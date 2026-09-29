"""
FR4 "Present & Verify": a holder presents a credential issued by Inji Certify
(Chirayu's certify/ flow) to Inji Verify over OpenID4VP, and the playground
reports what Inji Verify decided next to its own independent checks.

    verifier (this script, as the relying-party backend)
      1. POST /vp-request            -> openid4vp:// request (nonce, presentation_definition)
    wallet (wallet.py, the built-in holder wallet)
      2. reads the request, finds a matching credential
      3. builds the presentation (JSON-LD VP signed with the holder key, or SD-JWT + KB-JWT)
      4. POST response_uri (direct_post)
    verifier
      5. GET /vp-request/{id}/status (long poll until VP_SUBMITTED)
      6. POST /v2/vp-results/{txn}   -> Inji Verify's verdict
    playground
      7. independent checks (checks.py), outcome, suspected gaps

Scenarios (negative tests):
  none        honest presentation                                expected VALID
  altered     wallet changes farmerID after issuance             expected INVALID
  replay      presentation from session 1 re-sent to session 2   expected INVALID
  wrong_type  verifier asks for another credential type          expected INVALID

Like run_issuance(), run_presentation() never raises: failures come back as
{"ok": False, "error": ...} with every step taken so far.
"""
import base64
import io
import os
import logging
import secrets
import threading
import time

import requests

import checks as independent
import pex
from steps import StepLog
from verifier_client import VerifierClient
from wallet import PRESENTABLE, HolderWallet, WalletError

logger = logging.getLogger(__name__)

VALID_FORMATS = ["ldp_vc", "vc+sd-jwt", "mso_mdoc"]
SOURCES = ["wallet", "certify", "test"]

SCENARIOS = {
    "none": {"label": "Honest presentation", "expected": "VALID",
             "explain": "The wallet presents the credential exactly as issued, bound to this session's nonce."},
    "altered": {"label": "Altered credential", "expected": "INVALID",
                "explain": "The wallet changes farmerID to 000000000 after issuance, then signs the presentation as usual. "
                           "The holder signature is fine; the issuer's signature (or SD-JWT digest) no longer matches."},
    "replay": {"label": "Replayed presentation", "expected": "INVALID",
               "explain": "A presentation made for session 1 (its nonce) is captured and sent again to a new session 2."},
    "wrong_type": {"label": "Wrong credential type", "expected": "INVALID",
                   "explain": "The verifier asks for a LandOwnershipCredential. The wallet sends its FarmerCredential anyway, "
                              "as a careless or malicious wallet might."},
    "forged_issuer": {"label": "Forged issuer", "expected": "INVALID",
                      "explain": "Someone makes their own FarmerCredential that names Certify as the issuer but signs it with "
                                 "their own key (JSON-LD: their own did:key; SD-JWT: a self-signed x5c certificate)."},
    "expired": {"label": "Expired credential", "expected": "EXPIRED",
                "explain": "A genuine, correctly signed credential whose expiry date has passed, presented honestly. Certify "
                           "can't issue one that's already expired, so the offline test issuer signs it. Inji Verify should "
                           "report it as valid but expired."},
}

MDOC_REASON = ("Inji Verify 0.18.2 cannot take an mDoc over OpenID4VP: its direct_post handler only accepts JSON-LD "
               "presentations and SD-JWTs (VerifiablePresentationSubmissionServiceImpl.processSingleToken), so an mDoc "
               "DeviceResponse is dropped as INVALID_VP_TOKEN. Inji Verify checks mDocs only by QR/upload.")

# Findings a failed independent check most likely points at (docs/FINDINGS.md)
KNOWN_GAPS = {
    "constraints": "F2", "kb_nonce": "F3", "kb_aud": "F3", "kb_fresh": "F3", "issuer_key_binding": "F10",
}


def run_presentation(vc_format: str, scenario: str = "none", source: str = None,
                     wallet: HolderWallet = None, verifier: VerifierClient = None) -> dict:
    log = StepLog()
    base = {"format": vc_format, "scenario": scenario, "scenario_info": SCENARIOS.get(scenario), "steps": log.steps}
    if vc_format not in VALID_FORMATS:
        return {**base, "ok": False, "error": f"unknown format {vc_format!r}, expected one of {VALID_FORMATS}"}
    if vc_format == "mso_mdoc":
        return {**base, "ok": False, "error": MDOC_REASON}
    if scenario not in SCENARIOS:
        return {**base, "ok": False, "error": f"unknown scenario {scenario!r}, expected one of {list(SCENARIOS)}"}
    try:
        wallet = wallet or HolderWallet()
        verifier = verifier or VerifierClient()
        return _run(vc_format, scenario, source, wallet, verifier, log, base)
    except (requests.RequestException, WalletError, KeyError, ValueError, TypeError) as e:
        logger.exception("presentation flow failed")
        return {**base, "ok": False, "error": f"{type(e).__name__}: {e}"}


def _ensure_credential(vc_format, source, wallet, log):
    if source is None:
        source = "wallet" if vc_format in wallet.credentials else "certify"
    if source == "certify":
        result = wallet.receive_from_certify(vc_format)
        for s in result.get("steps", []):
            log.steps.append({**s, "actor": "issuer", "name": "Issuance: " + s["name"]})
        if not result.get("ok"):
            return f"could not get a credential from Certify: {result.get('error')}"
    elif source == "test":
        wallet.receive_from_test_issuer(vc_format)
        log.local("Receive a credential from the offline test issuer", "wallet",
                  {"issuer": "did:key (test issuer)", "note": "Not a Certify credential. Use it when Certify is unavailable."})
    elif vc_format not in wallet.credentials:
        return f"the wallet has no {vc_format} credential yet: receive one from Certify first"
    entry = wallet.credentials[vc_format]
    log.local("Wallet holds the credential", "wallet",
              {"source": entry["source"], "received_at": entry["received_at"],
               "bound_to_wallet_key": entry["bound_to_wallet_key"]},
              ok=entry["bound_to_wallet_key"],
              note=None if entry["bound_to_wallet_key"] else
              "This credential is bound to a different key, so the wallet cannot make a valid holder proof for it.")
    return None


def _present_once(vc_format, pd, wallet, verifier, log, tag="", alter=False, force=False, presentation=None):
    """One verifier session. With `presentation` given, that (old) presentation is
    replayed into the new session instead of building a fresh one."""
    session = verifier.create_request(log, pd, label="Verifier creates a presentation request" + tag)
    if session is None:
        return None, None, None, "Inji Verify refused to create the request (see the step's response)"
    request = wallet.read_request(session["authorization_request_uri"])
    log.local("Wallet reads the request" + tag, "wallet",
              {"openid4vp_uri": session["authorization_request_uri"], "client_id": request.get("client_id"),
               "nonce": request.get("nonce"), "response_uri": request.get("response_uri"),
               "presentation_definition": request.get("presentation_definition")},
              note="Exactly what a phone wallet would get from the QR code.")
    descriptor, reasons = wallet.match(request, vc_format)
    if reasons:
        log.local("Wallet matches its credential to the request" + tag, "wallet",
                  {"matches": False, "reasons": reasons, "action": "sending it anyway (negative test)" if force else "stopping"},
                  ok=False)
        if not force:
            return session, request, None, "the wallet has no credential that matches this request: " + "; ".join(reasons)
    else:
        log.local("Wallet matches its credential to the request" + tag, "wallet", {"matches": True, "descriptor": descriptor.get("id")})

    if presentation is None:
        presentation = wallet.build_presentation(request, vc_format, descriptor, alter=alter)
        log.local("Wallet builds and signs the presentation" + tag, "wallet",
                  {**presentation["summary"], "presentation_submission": presentation["presentation_submission"]})
    else:
        # the replayed copy keeps its old nonce; only the routing (state) is new
        presentation = {**presentation, "presentation_submission": {**presentation["presentation_submission"],
                                                                     "definition_id": pd["id"]}}
        log.local("Attacker re-sends the captured presentation" + tag, "wallet",
                  {"note": "Same signed vp_token as session 1 (old nonce). Only the unsigned routing fields (state, definition_id) are changed to session 2's."})
    response = wallet.submit(log, request, presentation, label="Wallet sends the presentation (direct_post)" + tag)
    return session, request, (presentation, response), None


def _verifier_verdict(session, submit_response, verifier, log, tag=""):
    if submit_response is None:
        return {"status": "ERROR", "detail": "could not reach the verifier's response_uri", "checks": [], "claims": {}}
    if submit_response.status_code >= 400:
        try:
            body = submit_response.json()
            detail = f"{body.get('errorCode', '')} {body.get('errorMessage', '')}".strip()
        except ValueError:
            detail = submit_response.text[:200]
        return {"status": "REJECTED", "detail": f"refused at submission (HTTP {submit_response.status_code}) {detail}".strip(),
                "checks": [], "claims": {}}
    status = verifier.wait_for_submission(log, session["request_id"], label="Verifier waits for the wallet's answer" + tag)
    if status != "VP_SUBMITTED":
        return {"status": "ERROR" if status != "EXPIRED" else "EXPIRED", "detail": f"request status {status}", "checks": [], "claims": {}}
    return verifier.fetch_result(log, session["transaction_id"], label="Verifier fetches Inji Verify's result" + tag)


def outcome_for(scenario, verifier_result, playground_checks):
    expected = SCENARIOS[scenario]["expected"]
    status = verifier_result.get("status")
    if status == "EXPIRED":
        effective = "EXPIRED" if expected == "EXPIRED" else "INVALID"
    else:
        effective = "INVALID" if status == "REJECTED" else status
    if status == "ERROR":
        verdict = "ERROR"
    else:
        verdict = "PASS" if effective == expected else "FAIL"
    failed = [c for c in playground_checks if c["ok"] is False]
    gaps = []
    if status == "VALID" and failed:
        gaps.append({
            "summary": "Inji Verify accepted the presentation although the playground's checks failed: "
                       + "; ".join(c["label"] for c in failed),
            "failed_checks": [c["id"] for c in failed],
            "finding": sorted({KNOWN_GAPS[c["id"]] for c in failed if c["id"] in KNOWN_GAPS}) or None,
        })
    holder_checked = any(c["id"] in ("holder_signature", "kb_signature") for c in playground_checks)
    holder_failed_at_verifier = any("Holder" in (c.get("label") or "") and not c.get("ok")
                                    for c in verifier_result.get("checks") or [])
    if expected == "VALID" and status in ("INVALID", "REJECTED") and not failed and holder_failed_at_verifier and not holder_checked:
        gaps.append({
            "summary": "Inji Verify rejected the holder's proof: " + (verifier_result.get("detail") or "no detail")
                       + ". With a real wallet the playground never sees the presentation, so it can't check this itself. "
                       "Most likely the wallet signed with a different key than the one the credential is bound to "
                       "(Inji Web / Mimoto 0.22 always signs with its Ed25519 key, see W3) - a wallet-side problem, "
                       "and Inji Verify is right to reject it.",
            "failed_checks": [], "finding": ["W3"],
        })
    elif expected == "VALID" and status in ("INVALID", "REJECTED") and not failed:
        gaps.append({
            "summary": "Inji Verify rejected a presentation the playground found valid: "
                       + (verifier_result.get("detail") or "no detail") + ". Could be a verifier limitation "
                       "(e.g. proof types it cannot check, F8) or setup (issuer DID document not reachable from the container).",
            "failed_checks": [], "finding": None,
        })
    return {"expected": expected, "result": status, "verdict": verdict,
            "explanation": SCENARIOS[scenario]["explain"]}, gaps


def _run(vc_format, scenario, source, wallet, verifier, log, base):
    if scenario in ("forged_issuer", "expired"):
        return _run_with_test_credential(vc_format, scenario, wallet, verifier, log, base)
    err = _ensure_credential(vc_format, source, wallet, log)
    if err:
        return {**base, "ok": False, "error": err}

    wanted_type = pex.WRONG_TYPE if scenario == "wrong_type" else pex.FARMER_TYPE
    pd = pex.build_presentation_definition(vc_format, wanted_type)

    if scenario == "replay":
        s1, _, sent1, e = _present_once(vc_format, pd, wallet, verifier, log, tag=" [session 1]")
        if e:
            return {**base, "ok": False, "error": e}
        first = _verifier_verdict(s1, sent1[1], verifier, log, tag=" [session 1]")
        log.local("Session 1 result (the original, honest presentation)", "playground", {"inji_verify": first["status"]})
        pd2 = pex.build_presentation_definition(vc_format, wanted_type)
        session, request, sent, e = _present_once(vc_format, pd2, wallet, verifier, log, tag=" [session 2, replay]",
                                                  presentation=sent1[0])
        tag = " [session 2, replay]"
    else:
        session, request, sent, e = _present_once(vc_format, pd, wallet, verifier, log,
                                                  alter=scenario == "altered", force=scenario == "wrong_type")
        tag = ""
    if e:
        return {**base, "ok": False, "error": e}
    return _finish(vc_format, scenario, session, sent, verifier, log, base, tag)


def _run_with_test_credential(vc_format, scenario, wallet, verifier, log, base):
    """Scenarios that need a credential Certify won't issue (forged issuer, already expired). The credential is
    used for this run only; the wallet's stored one is untouched."""
    from test_issuer import TestIssuer
    maker = TestIssuer()
    if scenario == "forged_issuer":
        cred = maker.issue(vc_format, wallet.did, forged=True)
        log.local("Attacker makes a credential that names Certify as issuer", "wallet",
                  {"claims_issuer": (cred.get("issuer") if isinstance(cred, dict) else "iss = Certify's issuer id"),
                   "actually_signed_by": maker.did if vc_format == "ldp_vc" else "a self-signed x5c certificate (no trust chain)",
                   "bound_to": "this wallet's key, so the holder proof is genuine"})
    else:
        cred = maker.issue(vc_format, wallet.did, expired=True)
        log.local("Test issuer signs a credential that has already expired", "issuer",
                  {"issuer": maker.did, "expired": (cred.get("expirationDate") if isinstance(cred, dict) else "exp is 1 day ago"),
                   "note": "Otherwise identical to the Farmer credential; signature and holder binding are genuine."})
    saved = wallet.credentials.get(vc_format)
    wallet.credentials[vc_format] = {"format": vc_format, "credential": cred, "source": f"{scenario} (test)",
                                     "received_at": "", "bound_to_wallet_key": True}
    try:
        session, request, sent, e = _present_once(vc_format, pex.build_presentation_definition(vc_format), wallet, verifier, log)
    finally:
        if saved is None:
            wallet.credentials.pop(vc_format, None)
        else:
            wallet.credentials[vc_format] = saved
    if e:
        return {**base, "ok": False, "error": e}
    return _finish(vc_format, scenario, session, sent, verifier, log, base, "")


def _finish(vc_format, scenario, session, sent, verifier, log, base, tag):
    presentation, response = sent
    verifier_result = _verifier_verdict(session, response, verifier, log, tag=tag)
    submitted = {"vp_token": presentation["vp_token"], "presentation_submission": presentation["presentation_submission"],
                 "state": session["request_id"]}
    playground_checks = independent.run_checks(vc_format, session, submitted)
    log.local("Playground runs its own checks", "playground",
              {"passed": sum(1 for c in playground_checks if c["ok"]), "failed": sum(1 for c in playground_checks if c["ok"] is False),
               "not_run": sum(1 for c in playground_checks if c["ok"] is None)})
    outcome, gaps = outcome_for(scenario, verifier_result, playground_checks)
    return {**base, "ok": True, "error": None,
            "session": {k: session[k] for k in ("transaction_id", "request_id", "client_id", "nonce", "response_uri",
                                                "presentation_definition", "authorization_request_uri", "expires_at")},
            "presentation": presentation["summary"],
            "verifier_result": {k: v for k, v in verifier_result.items() if k != "raw"},
            "playground_checks": playground_checks, "outcome": outcome, "suspected_gaps": gaps}


# ------------------------------------------------------------ phone mode
# A real wallet app (e.g. Inji Wallet) scans the QR. We only see what Inji
# Verify reports back, so the independent checks run on the credential(s) it
# returns; nonce / holder-proof checks need a copy of the presentation and
# are marked "not run".

_PHONE = {}
_PHONE_LOCK = threading.Lock()


def qr_data_url(text: str) -> str:
    """QR code as an SVG data URL (no Pillow needed). None if qrcode isn't installed."""
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:
        return None
    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathFillImage, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()


INJI_WEB_URL = os.environ.get("INJI_WEB_URL", "http://localhost:3004").rstrip("/")


def inji_web_link(authorization_request_uri: str) -> str:
    """The same request as a link Inji Web (0.17) opens directly: its /user/authorize page takes
    the openid4vp query string and hands it to Mimoto's /wallets/{id}/presentations API."""
    query = authorization_request_uri.split("?", 1)[1] if "?" in authorization_request_uri else ""
    return f"{INJI_WEB_URL}/user/authorize?{query}"


def start_phone_session(vc_format: str, scenario: str = "none", verifier: VerifierClient = None) -> dict:
    log = StepLog()
    if vc_format not in PRESENTABLE:
        return {"ok": False, "error": MDOC_REASON if vc_format == "mso_mdoc" else f"unknown format {vc_format!r}", "steps": log.steps}
    if scenario not in ("none", "wrong_type"):
        return {"ok": False, "error": "with a phone wallet only 'none' and 'wrong_type' make sense (the others need a wallet that misbehaves on purpose)", "steps": log.steps}
    verifier = verifier or VerifierClient()
    pd = pex.build_presentation_definition(vc_format, pex.WRONG_TYPE if scenario == "wrong_type" else pex.FARMER_TYPE)
    session = verifier.create_request(log, pd, label="Verifier creates a presentation request")
    if session is None:
        return {"ok": False, "error": "Inji Verify refused to create the request", "steps": log.steps}
    sid = secrets.token_urlsafe(8)
    with _PHONE_LOCK:
        _PHONE[sid] = {"format": vc_format, "scenario": scenario, "session": session, "log": log, "verifier": verifier,
                       "created": time.time(), "result": None}
    return {"ok": True, "id": sid, "format": vc_format, "scenario": scenario,
            "authorization_request_uri": session["authorization_request_uri"],
            "inji_web_link": inji_web_link(session["authorization_request_uri"]),
            "qr": qr_data_url(session["authorization_request_uri"]),
            "response_uri": session["response_uri"], "steps": log.steps,
            "hint": "The phone must reach response_uri. If it says localhost, set VERIFY_PUBLIC_URL to this "
                    "computer's LAN address and restart the verify-service container."}


def poll_phone_session(sid: str) -> dict:
    with _PHONE_LOCK:
        entry = _PHONE.get(sid)
    if not entry:
        return {"ok": False, "error": "unknown session"}
    if entry["result"]:
        return entry["result"]
    verifier, session, log = entry["verifier"], entry["session"], entry["log"]
    status = verifier.status_once(session["request_id"])
    if status not in ("VP_SUBMITTED", "EXPIRED"):
        return {"ok": True, "done": False, "status": status, "steps": log.steps}
    log.local("Phone wallet answered", "verifier", {"status": status})
    if status == "EXPIRED":
        verifier_result = {"status": "EXPIRED", "detail": "the request expired before a wallet answered", "checks": [], "claims": {}}
    else:
        verifier_result = verifier.fetch_result(log, session["transaction_id"], label="Verifier fetches Inji Verify's result")
    playground_checks = independent.run_checks(entry["format"], session, None, verifier_result.get("credentials"))
    outcome, gaps = outcome_for(entry["scenario"], verifier_result, playground_checks)
    result = {"ok": True, "done": True, "format": entry["format"], "scenario": entry["scenario"],
              "scenario_info": SCENARIOS[entry["scenario"]], "steps": log.steps,
              "session": {k: session[k] for k in ("transaction_id", "request_id", "client_id", "nonce", "authorization_request_uri")},
              "verifier_result": {k: v for k, v in verifier_result.items() if k != "raw"},
              "playground_checks": playground_checks, "outcome": outcome, "suspected_gaps": gaps}
    entry["result"] = result
    return result
