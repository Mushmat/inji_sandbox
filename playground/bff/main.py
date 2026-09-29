"""Playground BFF: the one backend the Playground UI talks to.

    python playground/bff/main.py      then open http://localhost:5050
    API reference: http://localhost:5050/docs
"""

import config  # noqa: F401  (sets up paths and env before the certify/ and verify/ imports)

import logging
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import catalog
import health
import identity
import matrix
import report
import runner
import store
import verifier_service
from config import HOST, PORT, WEB_DIST

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="Inji Interoperability Playground BFF",
    description="Runs issue -> hold -> present -> verify across Inji Certify, Inji Web and Inji Verify, "
                "and records every protocol step and outcome.",
    version="1.0.0",
)
store.init()
app.include_router(verifier_service.router)


class RunRequest(BaseModel):
    issuer: Literal["certify_preauth", "certify", "test_issuer"]
    wallet: Literal["playground_wallet", "inji_web", "browser_wallet"]
    verifier: Literal["inji_verify", "playground_verifier"]
    format: Literal["ldp_vc", "vc+sd-jwt", "mso_mdoc"]
    scenario: Literal["none", "altered", "replay", "wrong_type", "forged_issuer", "expired"] = "none"


@app.get("/api/health", summary="Status of every module and whether Certify's keys match the published DID")
def get_health():
    return health.status()


@app.get("/api/catalog", summary="Issuers, wallets, verifiers, formats and scenarios")
def get_catalog():
    return catalog.catalog()


@app.post("/api/compatibility", summary="Whether a combination can run, and what limits apply")
def get_compatibility(req: RunRequest):
    return catalog.check(req.issuer, req.wallet, req.verifier, req.format, req.scenario)


@app.post("/api/runs", status_code=202, summary="Start a run; poll GET /api/runs/{id} for progress")
def start_run(req: RunRequest):
    try:
        return runner.start(req.issuer, req.wallet, req.verifier, req.format, req.scenario)
    except runner.RunBusy as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/api/runs", summary="Run history, newest first")
def list_runs(limit: int = 500):
    return store.history(limit)


@app.get("/api/runs/{run_id}", summary="One run with every protocol step")
def get_run(run_id: str):
    run = runner.get(run_id)
    if not run:
        raise HTTPException(404, "No run with that id.")
    return run


@app.post("/api/runs/{run_id}/continue", summary="Inji Web runs: the card is downloaded, start the presentation")
def continue_run(run_id: str):
    try:
        return runner.resume(run_id)
    except ValueError as e:
        raise HTTPException(409, str(e))


class DcApiStart(BaseModel):
    origin: str


@app.post("/api/runs/{run_id}/dc-api", summary="Digital Credentials API runs: build the request for this page's origin")
def dc_api_request(run_id: str, body: DcApiStart):
    try:
        return runner.dc_api_request(run_id, body.origin)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/api/runs/{run_id}/cancel", summary="Stop a run in progress")
def cancel_run(run_id: str):
    try:
        return runner.cancel(run_id)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.delete("/api/runs", status_code=204, summary="Clear the run history")
def clear_runs():
    store.clear()


@app.get("/api/report.md", response_class=PlainTextResponse, summary="Interoperability report as markdown")
def get_report(ids: str = ""):
    runs = store.history()
    if ids:  # just these runs, e.g. one matrix pass
        wanted = set(ids.split(","))
        runs = [r for r in runs if r["id"] in wanted]
    return PlainTextResponse(report.markdown(runs), media_type="text/markdown",
                             headers={"Content-Disposition": 'attachment; filename="interoperability-report.md"'})


class IdentityUpdate(BaseModel):
    fields: dict[str, str]
    reload_esignet: bool = False


@app.get("/api/identity", summary="The mock person credentials are issued for")
def get_identity():
    return identity.read()


@app.put("/api/identity", summary="Change the person. The eSignet Certify loads it on POST /api/identity/reload")
def put_identity(body: IdentityUpdate):
    try:
        return identity.save(body.fields, body.reload_esignet)
    except identity.InvalidIdentity as e:
        raise HTTPException(422, {"message": str(e), "errors": e.errors})
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/api/identity/reload", summary="Restart the eSignet Certify so it reads the saved person")
def reload_identity():
    return identity.reload()


@app.get("/api/identity/status", summary="Progress of the eSignet Certify restart, and whether it has the latest details")
def get_identity_status():
    return identity.restart_status()


class MatrixRequest(BaseModel):
    preset: Literal["quick", "full"] = "quick"


@app.get("/api/matrix", summary="Progress of the test matrix (FR14)")
def get_matrix():
    return {**matrix.status(), "sizes": {p: len(matrix.combinations(p)) for p in ("quick", "full")}}


@app.post("/api/matrix", status_code=202, summary="Run every automated combination, one after another")
def start_matrix(body: MatrixRequest):
    try:
        return matrix.start(body.preset)
    except runner.RunBusy as e:
        raise HTTPException(409, str(e))


@app.post("/api/matrix/cancel", summary="Stop the matrix after the current run")
def cancel_matrix():
    return matrix.cancel()


@app.get("/api/wallet", summary="What the Playground wallet currently holds")
def get_wallet():
    return runner.wallet_summary()


if (WEB_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    index = WEB_DIST / "index.html"
    if not index.exists():
        return PlainTextResponse("The UI isn't built yet: cd playground/web && npm install && npm run build", 503)
    target = WEB_DIST / path
    if path and target.is_file() and WEB_DIST in target.resolve().parents:
        return FileResponse(target)
    return FileResponse(index)


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
