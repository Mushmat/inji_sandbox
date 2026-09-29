"""The Playground verifier: a non-Inji OpenID4VP relying party (FR8).

Wallet-facing, it is plain OpenID4VP: an openid4vp:// request carrying a presentation_definition and a
nonce, answered by direct_post to response_uri. Its back end exposes the same four calls as Inji Verify's
verify-service, so verify/scripts/verifier_client.py and the scripted wallet drive either verifier unchanged
and the comparison is like for like. The verifying is done by verify/scripts/checks.py, which checks every
rule it knows, including the ones Inji Verify 0.18.2 skips (FINDINGS F2, F3, F10).
"""

import json
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import JSONResponse

import checks  # verify/scripts
import sdjwt  # verify/scripts
from config import PLAYGROUND_PUBLIC_URL

PREFIX = "/verifier/v1/verify"
CLIENT_ID = "playground-verifier"
REQUEST_TTL = timedelta(minutes=5)
LONG_POLL_SECONDS = 55

router = APIRouter(prefix=PREFIX, tags=["Playground verifier (OpenID4VP)"])
_sessions: dict = {}
_lock = threading.Lock()

HOLDER_CHECKS = {"holder_signature", "challenge", "domain", "holder_binding", "kb_present", "kb_signature",
                 "kb_nonce", "kb_aud", "kb_sd_hash", "kb_fresh"}


def response_uri() -> str:
    return f"{PLAYGROUND_PUBLIC_URL}{PREFIX}/vp-submission/direct-post"


def _now():
    return datetime.now(timezone.utc)


def _find(**kw):
    with _lock:
        key, value = next(iter(kw.items()))
        return next((s for s in _sessions.values() if s[key] == value), None)


def _expired(s) -> bool:
    return s["status"] == "ACTIVE" and _now() > s["expires_at"]


@router.post("/vp-request", status_code=201, summary="Open a presentation session")
def create_request(body: dict):
    pd = body.get("presentationDefinition")
    if not isinstance(pd, dict) or not pd.get("input_descriptors"):
        raise HTTPException(400, {"errorCode": "INVALID_PRESENTATION_DEFINITION",
                                  "errorMessage": "presentationDefinition needs at least one input descriptor"})
    s = {
        "transaction_id": f"txn_{uuid.uuid4()}",
        "request_id": f"req_{uuid.uuid4()}",
        "client_id": body.get("clientId") or CLIENT_ID,
        "nonce": body.get("nonce") or secrets.token_urlsafe(16),
        "presentation_definition": pd,
        "expires_at": _now() + REQUEST_TTL,
        "status": "ACTIVE",
        "submission": None,
    }
    with _lock:
        _sessions[s["request_id"]] = s
    return {
        "transactionId": s["transaction_id"],
        "requestId": s["request_id"],
        "expiresAt": int(s["expires_at"].timestamp() * 1000),
        "authorizationDetails": {
            "clientId": s["client_id"],
            "nonce": s["nonce"],
            "responseUri": response_uri(),
            "responseMode": "direct_post",
            "responseType": "vp_token",
            "presentationDefinition": pd,
        },
    }


@router.get("/vp-request/{request_id}/status", summary="Long poll until the wallet answers")
def status(request_id: str):
    deadline = time.monotonic() + LONG_POLL_SECONDS
    while True:
        s = _find(request_id=request_id)
        if not s:
            raise HTTPException(404, {"errorCode": "INVALID_REQUEST_ID", "errorMessage": "no such request"})
        if _expired(s):
            s["status"] = "EXPIRED"
        if s["status"] != "ACTIVE" or time.monotonic() > deadline:
            return {"status": s["status"]}
        time.sleep(0.4)


def _format_of(vp_token):
    if isinstance(vp_token, dict):
        return "ldp_vc"
    text = str(vp_token).strip()
    return "ldp_vc" if text.startswith("{") else "vc+sd-jwt"


def _presented_nonce(fmt, vp_token):
    """The nonce the holder signed: proof.challenge (JSON-LD) or the KB-JWT's nonce (SD-JWT)."""
    try:
        if fmt == "ldp_vc":
            vp = vp_token if isinstance(vp_token, dict) else json.loads(vp_token)
            return (vp.get("proof") or {}).get("challenge")
        kb = sdjwt.parse(vp_token)["kb_jwt"]
        return sdjwt.decode_jwt_part(kb.split(".")[1]).get("nonce") if kb else None
    except (ValueError, KeyError, IndexError, TypeError):
        return None


@router.post("/vp-submission/direct-post", summary="The wallet's answer (OpenID4VP direct_post)")
def direct_post(vp_token: str = Form(...), presentation_submission: str = Form(...), state: str = Form(...)):
    s = _find(request_id=state)
    if not s:
        return JSONResponse({"errorCode": "INVALID_REQUEST", "errorMessage": "state doesn't match an open request"}, 400)
    if _expired(s):
        s["status"] = "EXPIRED"
    if s["status"] != "ACTIVE":
        return JSONResponse({"errorCode": "REQUEST_CLOSED", "errorMessage": f"request is {s['status']}"}, 400)
    try:
        submission = json.loads(presentation_submission)
    except ValueError:
        return JSONResponse({"errorCode": "INVALID_PRESENTATION_SUBMISSION", "errorMessage": "not JSON"}, 400)
    refused = _accept(s, vp_token, submission)
    return refused or {}


def _accept(s, vp_token, submission):
    """Stores the answer on the session, or returns the error response that refuses it."""
    fmt = _format_of(vp_token)
    # Checked here for both formats. A presentation signed for another session's nonce is a replay.
    if _presented_nonce(fmt, vp_token) != s["nonce"]:
        return JSONResponse({"errorCode": "NONCE_VALIDATION_FAILED",
                             "errorMessage": "the presentation isn't bound to this request's nonce"}, 400)
    s["submission"] = {"vp_token": vp_token, "presentation_submission": submission, "state": s["request_id"], "format": fmt}
    s["status"] = "VP_SUBMITTED"
    return None


def _category(results, ids):
    picked = [c for c in results if c["id"] in ids]
    failed = next((c for c in picked if c["ok"] is False), None)
    if not picked:
        return None
    return {"valid": failed is None,
            "error": None if failed is None else {"errorCode": failed["id"].upper(),
                                                  "errorMessage": f"{failed['label']}: {failed.get('detail') or 'failed'}"}}


def _credential_and_claims(fmt, vp_token):
    if fmt == "ldp_vc":
        vp = vp_token if isinstance(vp_token, dict) else json.loads(vp_token)
        vcs = vp.get("verifiableCredential") or []
        vc = vcs[0] if isinstance(vcs, list) and vcs else vcs
        subject = (vc or {}).get("credentialSubject") or {}
        return vc, {k: v for k, v in subject.items() if k not in ("id", "face")}
    p = sdjwt.parse(vp_token)
    view, _, _ = sdjwt.reconstruct(p["payload"], p["disclosures"])
    subject = view.get("credentialSubject") or view
    credential = p["presented_part"]
    return credential, {k: v for k, v in subject.items() if k not in ("_sd", "_sd_alg", "cnf", "face")}


@router.post("/v2/vp-results/{transaction_id}", summary="The verdict, in Inji Verify's v2 result shape")
def result(transaction_id: str, body: dict = None):
    s = _find(transaction_id=transaction_id)
    if not s:
        raise HTTPException(404, {"errorCode": "INVALID_TRANSACTION_ID", "errorMessage": "no such transaction"})
    if not s["submission"]:
        raise HTTPException(400, {"errorCode": "NO_SUBMISSION", "errorMessage": f"request is {s['status']}"})
    sub = s["submission"]
    results = checks.run_checks(sub["format"], s, sub)
    expiry = next((c for c in results if c["id"] == "expiry"), None)
    holder = _category(results, HOLDER_CHECKS)
    rest = _category(results, {c["id"] for c in results} - HOLDER_CHECKS - {"expiry"})
    credential, claims = _credential_and_claims(sub["format"], sub["vp_token"])
    all_ok = not any(c["ok"] is False for c in results)
    return {
        "transactionId": transaction_id,
        "allChecksSuccessful": all_ok,
        "credentialResults": [{
            "verifiableCredential": credential,
            "allChecksSuccessful": all_ok,
            "holderProofCheck": holder,
            "schemaAndSignatureCheck": rest,
            "expiryCheck": {"valid": expiry is None or expiry["ok"] is not False},
            "statusCheck": [],
            "claims": claims if (body or {}).get("includeClaims", True) else {},
        }],
        "checks": results,
    }


# ------------------------------------------------------------------ Digital Credentials API (FR13)
# The browser's navigator.credentials.get({digital}) asks the wallets on the device (or a phone paired
# with it) and hands the answer back to the page, which posts it here. OpenID4VP's DC API mode:
# response_mode dc_api, no client_id, and the holder binds the answer to the page's origin
# (aud / domain = "origin:<origin>"). Both the OpenID4VP 1.0 request (DCQL) and the older draft
# (presentation_definition) are offered; the wallet answers whichever it speaks.

VP_FORMATS_SUPPORTED = {
    "ldp_vc": {"proof_type_values": ["Ed25519Signature2020", "JsonWebSignature2020"]},
    "dc+sd-jwt": {"sd-jwt_alg_values": ["EdDSA", "ES256", "RS256"], "kb-jwt_alg_values": ["ES256", "EdDSA", "RS256"]},
}


def _dcql(fmt: str) -> dict:
    if fmt == "ldp_vc":
        query = {"id": "farmer", "format": "ldp_vc",
                 "meta": {"type_values": [["VerifiableCredential", "FarmerCredential"]]},
                 "claims": [{"path": ["credentialSubject", "farmerID"]}]}
    else:
        query = {"id": "farmer", "format": "dc+sd-jwt", "meta": {"vct_values": ["FarmerCredentialSdJwt"]},
                 "claims": [{"path": ["farmerID"]}]}
    return {"credentials": [query]}


def create_dc_request(fmt: str, origin: str) -> dict:
    import pex  # verify/scripts
    pd = pex.build_presentation_definition(fmt)
    s = {
        "transaction_id": f"txn_{uuid.uuid4()}",
        "request_id": f"req_{uuid.uuid4()}",
        "client_id": f"origin:{origin}",
        "nonce": secrets.token_urlsafe(16),
        "presentation_definition": pd,
        "expires_at": _now() + REQUEST_TTL,
        "status": "ACTIVE",
        "submission": None,
    }
    with _lock:
        _sessions[s["request_id"]] = s
    common = {"response_type": "vp_token", "response_mode": "dc_api", "nonce": s["nonce"]}
    requests = [
        {"protocol": "openid4vp-v1-unsigned",
         "data": {**common, "dcql_query": _dcql(fmt), "client_metadata": {"vp_formats_supported": VP_FORMATS_SUPPORTED}}},
        {"protocol": "openid4vp",
         "data": {**common, "presentation_definition": pd,
                  "client_metadata": {"vp_formats": {"ldp_vp": VP_FORMATS_SUPPORTED["ldp_vc"], "vc+sd-jwt": VP_FORMATS_SUPPORTED["dc+sd-jwt"]}}}},
    ]
    return {"transactionId": s["transaction_id"], "requestId": s["request_id"], "expected_origin": origin,
            "requests": requests}


def _unwrap_dc_response(s, protocol, data):
    """(vp_token, presentation_submission) from either protocol's answer."""
    if isinstance(data, str):
        data = json.loads(data)
    token = data["vp_token"]
    if str(protocol).startswith("openid4vp-v1"):  # OpenID4VP 1.0 / DCQL: {query id: [presentation, ...]}
        token = next(iter(token.values()))
    if isinstance(token, list):
        token = token[0]
    if isinstance(token, dict):
        token = json.dumps(token)
    pd = s["presentation_definition"]
    submission = data.get("presentation_submission") or {
        # DCQL answers carry no presentation_submission; this maps the one query onto the one descriptor.
        "id": str(uuid.uuid4()), "definition_id": pd["id"],
        "descriptor_map": [{"id": pd["input_descriptors"][0]["id"], "format": _format_of(token), "path": "$"}]}
    if isinstance(submission, str):
        submission = json.loads(submission)
    return token, submission


@router.post("/dc-api/{request_id}/response", summary="The wallet's answer through the Digital Credentials API")
def dc_api_response(request_id: str, body: dict):
    s = _find(request_id=request_id)
    if not s:
        return JSONResponse({"errorCode": "INVALID_REQUEST", "errorMessage": "no such request"}, 400)
    if _expired(s) or s["status"] != "ACTIVE":
        return JSONResponse({"errorCode": "REQUEST_CLOSED", "errorMessage": "this request is closed"}, 400)
    try:
        token, submission = _unwrap_dc_response(s, body.get("protocol"), body.get("data"))
    except (KeyError, ValueError, TypeError, StopIteration, IndexError) as e:
        return JSONResponse({"errorCode": "INVALID_VP_TOKEN", "errorMessage": f"unreadable answer: {e}"}, 400)
    return _accept(s, token, submission) or {"status": "VP_SUBMITTED", "protocol": body.get("protocol")}
