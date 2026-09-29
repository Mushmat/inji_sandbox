"""Runs one issue -> hold -> present -> verify cycle for a chosen issuer, wallet and verifier.

The protocol work is done by the existing, tested modules: certify/scripts/issuance_flow.py
(through the Playground wallet) and verify/scripts/presentation_flow.py. This module only
sequences them, labels every step with its phase and its sender/receiver, and records the result.
"""

import json
import logging
import re
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import quote

import requests

import catalog
import identity
import store
from config import CERTIFY_PUBLIC_ISSUER, CERTIFY_URL, INJI_WEB_URL, PORT, ROOT, VERSIONS

import issuance_flow  # certify/scripts
import checks  # verify/scripts
import presentation_flow  # verify/scripts
import verifier_service
from steps import StepLog
from verifier_client import VerifierClient
from wallet import PRESENTABLE, HolderWallet

logger = logging.getLogger(__name__)

CONFIG_IDS = {"ldp_vc": "FarmerCredential", "vc+sd-jwt": "FarmerCredentialSdJwt", "mso_mdoc": "MobileDrivingLicense"}
PHONE_TIMEOUT_S = 6 * 60

_wallet = HolderWallet()
_wallet_lock = threading.Lock()  # the Playground wallet is shared state
_registry_lock = threading.Lock()
_active: dict = {}


class RunBusy(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _target(url: str):
    if not url:
        return None
    if "esignet" in url:
        return "auth_server"
    if "/certify" in url or ":8090" in url:
        return "issuer"
    if "/verify" in url or "trycloudflare" in url:
        return "verifier"
    return None


def _presentation_phase(name: str) -> str:
    n = name.lower()
    if "holds the credential" in n:
        return "hold"
    if "test issuer signs" in n or "attacker makes" in n:
        return "issue"
    if any(k in n for k in ("waits", "fetches", "runs its own checks", "result", "answered")):
        return "verify"
    return "present"


class Run:
    """One run. `segments` hold the raw step lists as the flows fill them in, so a
    poll mid-run already shows the steps taken so far."""

    def __init__(self, issuer, wallet, verifier, fmt, scenario, compat):
        self.doc = {
            "id": uuid.uuid4().hex[:12], "created_at": _now(), "finished_at": None, "duration_ms": None,
            "status": "running", "phase": "issue", "issuer": issuer, "wallet": wallet, "verifier": verifier,
            "format": fmt, "scenario": scenario, "versions": VERSIONS, "compat": compat,
            "credential": None, "proof_type": None, "outcome": None, "verifier_result": None,
            "playground_checks": [], "suspected_gaps": [], "unsupported": None, "awaiting": None, "error": None,
            # FR16: how long each half took. Left empty for Inji Web runs, where a person sets the pace.
            "timings": {},
        }
        self.segments = []
        self._t0 = time.monotonic()

    def segment(self, kind: str, steps: list = None) -> list:
        steps = steps if steps is not None else []
        self.segments.append((kind, steps))
        return steps

    def local(self, phase, sender, receiver, name, detail, ok=True, note=None):
        entry = {"name": name, "method": "LOCAL", "url": None, "status": None, "ok": ok, "response": detail,
                 "phase": phase, "from": sender, "to": receiver}
        if note:
            entry["note"] = note
        self.segment("local", [entry])

    def steps(self) -> list:
        out = []
        verifier_name = catalog.VERIFIERS[self.doc["verifier"]]["name"]
        for kind, raw in self.segments:
            for s in list(raw):
                step = dict(s)
                if kind == "issuance":
                    step.setdefault("phase", "issue")
                    step["from"], step["to"] = step.get("from") or "wallet", _target(step.get("url"))
                elif kind == "presentation":
                    step["phase"] = _presentation_phase(step.get("name", ""))
                    actor = step.get("actor")
                    if step.get("method") == "LOCAL":
                        step["from"] = step["to"] = {"verifier": "relying_party"}.get(actor, actor)
                    elif actor == "verifier":
                        step["from"], step["to"] = "relying_party", "verifier"
                    else:
                        step["from"], step["to"] = actor, _target(step.get("url"))
                if verifier_name != "Inji Verify":
                    # the presentation flow's labels were written with Inji Verify in mind
                    for k in ("name", "note"):
                        if isinstance(step.get(k), str):
                            # but not where the text means Inji Verify's SDK itself
                            step[k] = re.sub(r"Inji Verify(?! SDK)", verifier_name, step[k])
                step["seq"] = len(out) + 1
                out.append(step)
        return out

    def view(self) -> dict:
        return {**self.doc, "steps": self.steps()}

    def finish(self, status="done"):
        self.doc["status"] = status
        self.doc["phase"] = "done"
        self.doc["awaiting"] = None
        self.doc["finished_at"] = _now()
        self.doc["duration_ms"] = int((time.monotonic() - self._t0) * 1000)


# ------------------------------------------------------------------ public API

def start(issuer, wallet, verifier, fmt, scenario) -> dict:
    compat = catalog.check(issuer, wallet, verifier, fmt, scenario)
    if not compat["runnable"]:
        raise ValueError(" ".join(compat["blockers"]))
    if (issuer == "certify" or wallet == "inji_web") and identity.certify_restarting():  # the pre-auth instance doesn't restart
        raise RunBusy("Certify is restarting to load the new credential details. Try again when it's back.")
    with _registry_lock:
        busy = [r for r in _active.values() if r.doc["status"] in ("running", "waiting")]
        if busy:
            raise RunBusy(f"Run {busy[0].doc['id']} is still in progress. Wait for it or cancel it first.")
        run = Run(issuer, wallet, verifier, fmt, scenario, compat)
        _active[run.doc["id"]] = run
    store.save(run.view())
    if catalog.WALLETS[wallet].get("brings_own_credential"):
        target = _dc_api_prepare
    elif catalog.WALLETS[wallet]["interactive"]:
        target = _interactive_issue
    else:
        target = _automatic
    threading.Thread(target=_guard, args=(run, target), daemon=True).start()
    return run.view()


def get(run_id: str):
    run = _active.get(run_id)
    return run.view() if run else store.get(run_id)


def resume(run_id: str) -> dict:
    """The person has the card in Inji Web: move on to the presentation."""
    run = _active.get(run_id)
    if not run or run.doc["status"] != "waiting" or (run.doc["awaiting"] or {}).get("kind") != "inji_web_issue":
        raise ValueError("This run isn't waiting for an Inji Web download.")
    run.doc["status"] = "running"
    run.doc["awaiting"] = None
    threading.Thread(target=_guard, args=(run, _interactive_present), daemon=True).start()
    return run.view()


def recover_interrupted():
    """Runs live in this process. One saved as in progress when the Playground stopped can never
    finish, so close it on startup instead of leaving the bench locked on it."""
    for summary in store.history():
        if summary["status"] in ("running", "waiting"):
            _close_orphan(summary["id"], "Stopped: the Playground restarted while this run was in progress.")


def _close_orphan(run_id: str, reason: str):
    doc = store.get(run_id)
    if not doc:
        return None
    doc.update(status="error", phase="done", awaiting=None, error=reason, finished_at=_now())
    store.save(doc)
    return doc


def cancel(run_id: str) -> dict:
    run = _active.get(run_id)
    if not run:
        saved = store.get(run_id)
        if saved and saved["status"] in ("running", "waiting"):
            return _close_orphan(run_id, "Cancelled.")
    if not run or run.doc["status"] not in ("running", "waiting"):
        raise ValueError("Only a run in progress can be cancelled.")
    run.doc["error"] = "Cancelled."
    run.finish("cancelled")
    store.save(run.view())
    return run.view()


def wallet_summary() -> dict:
    return _wallet.summary()


# ------------------------------------------------------------------ flows

def _guard(run: Run, fn):
    try:
        fn(run)
    except Exception as e:  # a run must always end in a stored state, never hang as "running"
        logger.exception("run %s failed", run.doc["id"])
        run.doc["error"] = f"{type(e).__name__}: {e}"
        run.finish("error")
    if run.doc["status"] in ("done", "error", "cancelled"):
        store.save(run.view())


def _automatic(run: Run):
    fmt = run.doc["format"]
    with _wallet_lock:
        t0 = time.monotonic()
        if not _issue_to_playground_wallet(run):
            return
        run.doc["timings"]["issue_ms"] = int((time.monotonic() - t0) * 1000)
        if _cancelled(run):
            return
        run.doc["phase"] = "present"
        reason = _presentation_blocker(run)
        if reason:
            _record_unsupported(run, reason)
            return
        t1 = time.monotonic()
        with _live_steps(run):
            result = presentation_flow.run_presentation(fmt, run.doc["scenario"], source="wallet", wallet=_wallet,
                                                        verifier=_verifier_client(run))
        run.doc["timings"]["present_verify_ms"] = int((time.monotonic() - t1) * 1000)
    if _cancelled(run):
        return
    _apply_result(run, result)


def _issue_to_playground_wallet(run: Run) -> bool:
    fmt, issuer = run.doc["format"], run.doc["issuer"]
    if issuer == "test_issuer":
        result = _wallet.receive_from_test_issuer(fmt, subject=identity.subject())
        cred = result["credential"]
        run.local("issue", "issuer", "wallet", "Test issuer signs the credential and hands it to the wallet",
                  {"issuer": "did:key test issuer (not Inji)", "format": fmt, "credential": cred},
                  note="No OpenID4VCI here: the test issuer exists to show a verifier handling a stranger's credential.")
    elif issuer == "certify_preauth":
        claims = identity.read()["identity"]
        result = issuance_flow.run_preauth_issuance(fmt, claims, holder_key=_wallet.key)
        run.segment("issuance", result.get("steps", []))
        if not result.get("ok"):
            run.doc["error"] = f"Issuance failed: {result.get('error')}"
            run.finish("error")
            return False
        cred = result["credential"]
        if fmt in PRESENTABLE:
            _wallet.store(fmt, cred, "Inji Certify (pre-authorized offer)")
    else:
        _offer_and_metadata(run, fmt)
        result = _wallet.receive_from_certify(fmt)
        run.segment("issuance", result.get("steps", []))
        if not result.get("ok"):
            run.doc["error"] = f"Issuance failed: {result.get('error')}"
            run.finish("error")
            return False
        cred = result["credential"]

    run.doc["phase"] = "hold"
    run.doc["credential"], run.doc["proof_type"] = _describe(fmt, cred, result.get("credential_decoded"))
    held = {"format": fmt, **run.doc["credential"],
            "stored": fmt in PRESENTABLE,
            "holder": _wallet.did}
    run.local("hold", "wallet", "wallet", "Wallet stores the credential", held,
              note="Bound to the wallet's own EC P-256 key, so it can prove possession later.")
    return True


def _offer_and_metadata(run: Run, fmt: str):
    offer = {
        "credential_issuer": CERTIFY_PUBLIC_ISSUER,
        "credential_configuration_ids": [CONFIG_IDS[fmt]],
        "grants": {"authorization_code": {"issuer_state": uuid.uuid4().hex}},
    }
    run.local("issue", "issuer", "wallet", "Issuer offers the credential",
              {"credential_offer": offer,
               "credential_offer_uri": "openid-credential-offer://?credential_offer=" + quote(json.dumps(offer))},
              note="Issuer-initiated offer (OpenID4VCI draft 13, section 4.1) for Certify's "
                   f"{CONFIG_IDS[fmt]} configuration, written by the Playground from Certify's metadata. "
                   "Certify 0.14 can also mint offers itself (pre-authorized code), which needs its own "
                   "authorization server switched on; this setup logs in through Collab's eSignet instead.")
    url = f"{CERTIFY_URL}/.well-known/openid-credential-issuer"
    try:
        r = requests.get(url, timeout=10)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:2000]
        run.segment("issuance", [{"name": "Wallet reads the issuer metadata", "method": "GET", "url": url,
                                  "status": r.status_code, "ok": r.ok, "response": body}])
    except requests.RequestException as e:
        run.segment("issuance", [{"name": "Wallet reads the issuer metadata", "method": "GET", "url": url,
                                  "status": None, "ok": False, "response": str(e)}])


def _presentation_blocker(run: Run):
    fmt = run.doc["format"]
    w, v = catalog.WALLETS[run.doc["wallet"]], catalog.VERIFIERS[run.doc["verifier"]]
    if fmt not in w["present"]:
        return next((l for l in run.doc["compat"]["limits"] if "present" in l), f"{w['name']} can't present {fmt}.")
    if fmt not in v["formats"]:
        return presentation_flow.MDOC_REASON if fmt == "mso_mdoc" else f"{v['name']} can't receive {fmt}."
    return None


def _record_unsupported(run: Run, reason: str):
    run.local("present", "playground", "playground", "Presentation not attempted", {"reason": reason}, ok=False)
    run.doc["unsupported"] = reason
    run.doc["outcome"] = {"expected": catalog.SCENARIOS[run.doc["scenario"]]["expected"], "result": "UNSUPPORTED",
                          "verdict": "UNSUPPORTED", "explanation": reason}
    run.finish()


def _apply_result(run: Run, result: dict):
    for key in ("verifier_result", "playground_checks", "suspected_gaps", "outcome", "session", "presentation"):
        if key in result:
            run.doc[key] = result[key]
    if not run.doc["proof_type"]:
        # Inji Web runs: the Playground never holds the credential, so read it from what Inji Verify returned
        creds = (run.doc.get("verifier_result") or {}).get("credentials") or []
        if creds and creds[0]:
            _, run.doc["proof_type"] = _describe(run.doc["format"], creds[0], None)
    if not result.get("ok"):
        run.doc["error"] = result.get("error")
        run.doc["outcome"] = run.doc.get("outcome") or {
            "expected": catalog.SCENARIOS[run.doc["scenario"]]["expected"], "result": "ERROR", "verdict": "ERROR",
            "explanation": result.get("error")}
    run.finish("done" if result.get("ok") else "error")


@contextmanager
def _live_steps(run: Run):
    """run_presentation() makes its own StepLog. Handing it one whose list is already
    registered on the run lets the UI show each step as it happens."""
    original = presentation_flow.StepLog

    def factory():
        log = original()
        run.segment("presentation", log.steps)
        return log

    presentation_flow.StepLog = factory
    try:
        yield
    finally:
        presentation_flow.StepLog = original


def _verifier_client(run: Run) -> VerifierClient:
    if run.doc["verifier"] == "playground_verifier":
        return VerifierClient(base_url=f"http://127.0.0.1:{PORT}{verifier_service.PREFIX}", client_id=verifier_service.CLIENT_ID)
    return VerifierClient()


def _cancelled(run: Run) -> bool:
    return run.doc["status"] == "cancelled"


# ------------------------------------------------------------------ Inji Web (a person drives the wallet)

def _interactive_issue(run: Run):
    fmt = run.doc["format"]
    entry = _mimoto_issuer_entry()
    run.local("issue", "issuer", "wallet", "Inji Web lists our Certify as an issuer",
              {"mimoto_issuers_config": entry, "credential_configuration_id": CONFIG_IDS[fmt]},
              note="Mimoto reads this entry, fetches Certify's metadata and runs the OpenID4VCI flow when you "
                   "download the card. That traffic stays inside Mimoto, so the Playground can't show it.")
    run.doc["status"] = "waiting"
    run.doc["awaiting"] = {
        "kind": "inji_web_issue",
        "title": "Download the card in Inji Web",
        "link": INJI_WEB_URL,
        "instructions": [
            "Open Inji Web and sign in with Google.",
            "Choose Farmer Issuer (Local Certify), then "
            + ("Farmer Verifiable Credential." if fmt == "ldp_vc" else "the SD-JWT Farmer credential."),
            "Log in with individual ID 2154189532 and OTP 111111.",
            "When the card shows in your wallet, come back and continue.",
        ],
    }


def _interactive_present(run: Run):
    fmt, scenario = run.doc["format"], run.doc["scenario"]
    run.doc["phase"] = "hold"
    run.local("hold", "wallet", "wallet", "Holder confirms the card is in Inji Web", {"format": fmt}, ok=True)
    run.doc["phase"] = "present"
    started = presentation_flow.start_phone_session(fmt, scenario, verifier=_verifier_client(run))
    seg = run.segment("presentation", list(started.get("steps", [])))
    if not started.get("ok"):
        run.doc["error"] = started.get("error")
        run.finish("error")
        return
    run.doc["status"] = "waiting"
    run.doc["awaiting"] = {
        "kind": "inji_web_present",
        "title": "Approve the presentation in Inji Web",
        "link": started["inji_web_link"],
        "instructions": ["Open the request in Inji Web.", "Pick the Farmer card and consent to share it.",
                         "This page picks up Inji Verify's result by itself."],
        "qr": started.get("qr"),
        "request_uri": started.get("authorization_request_uri"),
    }
    deadline = time.monotonic() + PHONE_TIMEOUT_S
    while time.monotonic() < deadline and not _cancelled(run):
        polled = presentation_flow.poll_phone_session(started["id"])
        seg[:] = polled.get("steps", seg)
        if polled.get("done") or not polled.get("ok", True):
            run.doc["status"] = "running"
            run.doc["phase"] = "verify"
            _apply_result(run, polled)
            return
        time.sleep(2)
    if not _cancelled(run):
        run.doc["error"] = "No answer from the wallet within six minutes."
        run.finish("error")


# ------------------------------------------------------------------ Digital Credentials API (FR13)

def _dc_api_prepare(run: Run):
    run.local("issue", "wallet", "wallet", "No issuance: the wallet brings its own credential",
              {"note": "The Playground can't put a credential into a wallet it doesn't control. The request asks for "
                       "a Farmer credential the wallet already holds."}, ok=True)
    run.doc["phase"] = "present"
    run.doc["status"] = "waiting"
    run.doc["awaiting"] = {
        "kind": "dc_api",
        "title": "Ask a wallet through the browser",
        "link": "",
        "instructions": [
            "Use a browser with the Digital Credentials API (recent Chrome or Edge; on a desktop it offers to use a phone).",
            "Press the button: the browser shows which wallets can answer.",
            "Pick one and approve. The answer comes back to this page and on to the Playground verifier.",
        ],
    }


def dc_api_request(run_id: str, origin: str) -> dict:
    run = _active.get(run_id)
    if not run or (run.doc["awaiting"] or {}).get("kind") != "dc_api" or run.doc["status"] != "waiting":
        raise ValueError("This run isn't waiting for a Digital Credentials API answer.")
    request = verifier_service.create_dc_request(run.doc["format"], origin.rstrip("/"))
    run.local("present", "relying_party", "relying_party", "Verifier builds a Digital Credentials API request",
              {"expected_origin": request["expected_origin"], "requests": request["requests"]},
              note="Two variants: OpenID4VP 1.0 with a DCQL query, and the earlier draft with a presentation_definition. "
                   "The browser passes them to the wallets; the answer is bound to this page's origin.")
    run.doc["awaiting"] = {**run.doc["awaiting"], "request_id": request["requestId"],
                           "response_url": f"{verifier_service.PREFIX}/dc-api/{request['requestId']}/response",
                           "requests": request["requests"]}
    threading.Thread(target=_guard, args=(run, lambda r: _dc_api_wait(r, request)), daemon=True).start()
    return run.view()


def _dc_api_wait(run: Run, request: dict):
    deadline = time.monotonic() + PHONE_TIMEOUT_S
    while time.monotonic() < deadline and not _cancelled(run):
        s = verifier_service._find(request_id=request["requestId"])
        if s and s["status"] == "VP_SUBMITTED":
            break
        time.sleep(1)
    else:
        if not _cancelled(run):
            run.doc["error"] = "No wallet answered within six minutes."
            run.finish("error")
        return
    run.doc["status"] = "running"
    run.doc["awaiting"] = None
    run.doc["phase"] = "verify"
    sub = s["submission"]
    run.local("present", "wallet", "relying_party", "Wallet answers through the browser",
              {"vp_token": sub["vp_token"], "presentation_submission": sub["presentation_submission"]})
    log = StepLog()
    run.segment("presentation", log.steps)
    verifier_result = _verifier_client(run).fetch_result(log, request["transactionId"], label="Verifier checks the answer")
    playground_checks = checks.run_checks(sub["format"], s, sub)
    outcome, gaps = presentation_flow.outcome_for("none", verifier_result, playground_checks)
    _apply_result(run, {"ok": True, "verifier_result": {k: v for k, v in verifier_result.items() if k != "raw"},
                        "playground_checks": playground_checks, "outcome": outcome, "suspected_gaps": gaps})


def _mimoto_issuer_entry() -> dict:
    path = ROOT / "wallet" / "docker-compose" / "config" / "mimoto-issuers-config.json"
    try:
        issuers = json.loads(path.read_text(encoding="utf-8-sig"))["issuers"]
        return next(i for i in issuers if i.get("issuer_id") == "FarmerIssuer")
    except (OSError, ValueError, StopIteration):
        return {"issuer_id": "FarmerIssuer", "note": "wallet/docker-compose/config/mimoto-issuers-config.json not readable"}


# ------------------------------------------------------------------ credential description

def _describe(fmt: str, cred, decoded):
    """(summary for the UI, proof type for the report)."""
    if fmt == "ldp_vc" and isinstance(cred, dict):
        proof = cred.get("proof") or {}
        issuer = cred.get("issuer")
        subject = {k: v for k, v in (cred.get("credentialSubject") or {}).items() if k != "face"}
        return ({"issuer": issuer if isinstance(issuer, str) else (issuer or {}).get("id"),
                 "types": cred.get("type"), "issued": cred.get("issuanceDate"), "expires": cred.get("expirationDate"),
                 "verification_method": proof.get("verificationMethod"), "claims": subject},
                proof.get("type"))
    if fmt == "vc+sd-jwt" and isinstance(cred, str):
        import sdjwt  # verify/scripts
        parsed = sdjwt.parse(cred)
        view, _, _ = sdjwt.reconstruct(parsed["payload"], parsed["disclosures"])
        header = parsed.get("header") or {}
        claims = {k: v for k, v in (view.get("credentialSubject") or view).items()
                  if k not in ("face", "_sd", "_sd_alg", "cnf")}
        return ({"issuer": view.get("iss"), "vct": view.get("vct"), "claims": claims,
                 "disclosable": [d["name"] for d in parsed["disclosures"]], "header": header},
                f"SD-JWT ({header.get('alg', '?')})")
    if fmt == "mso_mdoc":
        d = decoded or {}
        return ({"doctype": d.get("docType"), "claims": d.get("claims"), "signed": d.get("signed")},
                "COSE_Sign1 (mso_mdoc)")
    return ({"raw": cred}, None)
