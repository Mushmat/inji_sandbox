"""
Client for Inji Verify's verify-service (0.18.2), the relying-party side of
OpenID4VP (presentation_definition + direct_post).

Every endpoint and field name here was taken from the verify-service source
at tag v0.18.2 (VPRequestController, VPSubmissionController,
VPResultController and their DTOs):

  POST {base}/vp-request                     {clientId, nonce, presentationDefinition}
       -> 201 {transactionId, requestId, authorizationDetails{...}, expiresAt, requestUri?}
  GET  {base}/vp-request/{requestId}/status  long poll -> {status: ACTIVE | VP_SUBMITTED | EXPIRED}
  POST {base}/vp-submission/direct-post      form: vp_token, presentation_submission, state
                                             (the wallet calls this, not us; see wallet.py)
  POST {base}/v2/vp-results/{transactionId}  {includeClaims, skipStatusChecks, statusCheckFilters}
       -> {transactionId, allChecksSuccessful, credentialResults[...]}
  GET  {base}/vp-result/{transactionId}      v1 -> {vpResultStatus, vcResults[{vc, verificationStatus}]}

The openid4vp:// link is built the same way as the official
@mosip/react-inji-verify-sdk (OpenID4VPVerification): state is the requestId.
"""
import json
import os
import secrets
import time
from urllib.parse import urlencode

import requests

INJI_VERIFY_URL = os.environ.get("INJI_VERIFY_URL", "http://localhost:8080/v1/verify").rstrip("/")
CLIENT_ID = os.environ.get("VERIFY_CLIENT_ID", "inji-sandbox-playground")
REQUEST_TIMEOUT = 20
LONG_POLL_TIMEOUT = int(os.environ.get("VERIFY_LONG_POLL_SECONDS", "70"))

# What a wallet is told this verifier accepts (client_metadata.vp_formats),
# same list the Inji Verify SDK sends.
VP_FORMATS = {
    "ldp_vp": {"proof_type": ["Ed25519Signature2018", "Ed25519Signature2020", "RsaSignature2018", "JsonWebSignature2020"]},
    "vc+sd-jwt": {"sd-jwt_alg_values": ["RS256", "ES256", "ES256K", "EdDSA"], "kb-jwt_alg_values": ["RS256", "ES256", "ES256K", "EdDSA"]},
}


class VerifierClient:
    def __init__(self, base_url=None, client_id=None, session=None):
        self.base = (base_url or INJI_VERIFY_URL).rstrip("/")
        self.client_id = client_id or CLIENT_ID
        self.http = session or requests.Session()

    # ------------------------------------------------------------ request
    def create_request(self, log, presentation_definition, nonce=None, label="Create a presentation request"):
        """Returns a session dict, or None if Inji Verify refused (the step says why)."""
        nonce = nonce or secrets.token_urlsafe(16)
        url = f"{self.base}/vp-request"
        body = {"clientId": self.client_id, "nonce": nonce, "presentationDefinition": presentation_definition}
        try:
            r = self.http.post(url, json=body, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            log.error(label, "verifier", "POST", url, e, request=body)
            return None
        log.http(label, "verifier", "POST", url, r, request=body,
                 note="The verifier opens a session. Inji Verify stores the presentation_definition and nonce "
                      "and returns what a wallet needs to answer.")
        if r.status_code not in (200, 201):
            return None
        data = r.json()
        details = data.get("authorizationDetails") or {}
        return {
            "transaction_id": data["transactionId"],
            "request_id": data["requestId"],
            "client_id": details.get("clientId", self.client_id),
            "nonce": details.get("nonce", nonce),
            "response_uri": details.get("responseUri"),
            "response_mode": details.get("responseMode"),
            "response_type": details.get("responseType"),
            "presentation_definition": details.get("presentationDefinition") or presentation_definition,
            "presentation_definition_sent": presentation_definition,
            "presentation_definition_uri": details.get("presentationDefinitionUri"),
            "request_uri": data.get("requestUri"),
            "expires_at": data.get("expiresAt"),
            "authorization_request_uri": self.authorization_request_uri(data),
        }

    def authorization_request_uri(self, data: dict) -> str:
        details = data.get("authorizationDetails") or {}
        if data.get("requestUri"):
            params = {"client_id": self.client_id, "request_uri": data["requestUri"]}
        else:
            params = {
                "client_id": self.client_id,
                "state": data["requestId"],
                "response_mode": details.get("responseMode"),
                "response_type": details.get("responseType"),
                "nonce": details.get("nonce"),
                "response_uri": details.get("responseUri"),
            }
            if details.get("presentationDefinitionUri"):
                params["presentation_definition_uri"] = details["presentationDefinitionUri"]
            else:
                params["presentation_definition"] = json.dumps(details.get("presentationDefinition"), separators=(",", ":"))
            params["client_metadata"] = json.dumps({"client_name": self.client_id, "vp_formats": VP_FORMATS}, separators=(",", ":"))
        return "openid4vp://authorize?" + urlencode(params)

    # ------------------------------------------------------------- status
    def wait_for_submission(self, log, request_id, timeout_s=None, label="Wait for the wallet's answer"):
        timeout_s = timeout_s or LONG_POLL_TIMEOUT
        url = f"{self.base}/vp-request/{request_id}/status"
        deadline = time.time() + timeout_s
        polls = 0
        while time.time() < deadline:
            polls += 1
            try:
                r = self.http.get(url, timeout=min(LONG_POLL_TIMEOUT, max(5, deadline - time.time())))
            except requests.Timeout:
                continue
            except requests.RequestException as e:
                log.error(label, "verifier", "GET", url, e)
                return "ERROR"
            status = (r.json() or {}).get("status") if r.headers.get("content-type", "").startswith("application/json") else None
            if status in ("VP_SUBMITTED", "EXPIRED") or r.status_code >= 400:
                log.http(label + (f" (after {polls} polls)" if polls > 1 else ""), "verifier", "GET", url, r,
                         note="Long poll: Inji Verify holds this open until a wallet posts to the response_uri.")
                return status or "ERROR"
            time.sleep(1)
        log.local(label, "verifier", {"status": "TIMEOUT", "polls": polls, "waited_seconds": timeout_s}, ok=False)
        return "TIMEOUT"

    def status_once(self, request_id):
        """Non-blocking-ish status for the phone flow (short timeout)."""
        try:
            r = self.http.get(f"{self.base}/vp-request/{request_id}/status", timeout=3)
            return (r.json() or {}).get("status", "UNKNOWN")
        except (requests.RequestException, ValueError):
            return "ACTIVE"  # the long poll just hasn't returned yet

    # ------------------------------------------------------------- result
    def fetch_result(self, log, transaction_id, label="Fetch the verification result"):
        url = f"{self.base}/v2/vp-results/{transaction_id}"
        body = {"includeClaims": True, "skipStatusChecks": False, "statusCheckFilters": []}
        try:
            r = self.http.post(url, json=body, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            log.error(label, "verifier", "POST", url, e, request=body)
            return error_result(None, None, str(e))
        payload = _json(r)
        no_v2 = r.status_code in (404, 405) and not (isinstance(payload, dict) and payload.get("errorCode"))
        if not no_v2:
            log.http(label + " (v2)", "verifier", "POST", url, r, request=body,
                     note="Fetched server-side by transaction ID, as the Inji Verify SDK recommends.")
            return map_v2(payload) if r.status_code == 200 else error_result(payload, r.status_code)
        url = f"{self.base}/vp-result/{transaction_id}"
        r = self.http.get(url, timeout=REQUEST_TIMEOUT)
        log.http(label + " (v1)", "verifier", "GET", url, r)
        return map_v1(_json(r)) if r.status_code == 200 else error_result(_json(r), r.status_code)

    def health(self):
        try:
            r = self.http.get(f"{self.base}/vp-request/health-check/status", timeout=4)
            # Any HTTP answer (404 for an unknown request id) means the service is up.
            return {"ok": 0 < r.status_code < 500, "url": self.base, "detail": f"HTTP {r.status_code}"}
        except requests.RequestException as e:
            return {"ok": False, "url": self.base, "detail": str(e).split("(")[0][:160]}


def _json(r):
    try:
        return r.json()
    except ValueError:
        return r.text


def _err(e):
    if not e:
        return None
    return (f"{e.get('errorCode', '')} {e.get('errorMessage', '')}").strip() or None


def error_result(payload, status, detail=None):
    if isinstance(payload, dict):
        detail = detail or _err(payload)
    return {"status": "ERROR", "detail": detail or f"HTTP {status}", "checks": [], "claims": {}, "raw": payload}


def map_v2(b: dict) -> dict:
    """VPVerificationResultDto -> VALID / INVALID / EXPIRED."""
    creds = (b or {}).get("credentialResults") or []
    checks, claims = [], {}
    invalid, expired = len(creds) == 0, False
    for i, c in enumerate(creds):
        n = f" (credential {i + 1})" if len(creds) > 1 else ""
        if c.get("holderProofCheck") is not None:
            ok = bool(c["holderProofCheck"].get("valid"))
            checks.append({"label": "Holder proof" + n, "ok": ok, "detail": _err(c["holderProofCheck"].get("error"))})
            invalid |= not ok
        if c.get("schemaAndSignatureCheck") is not None:
            ok = bool(c["schemaAndSignatureCheck"].get("valid"))
            checks.append({"label": "Schema and issuer signature" + n, "ok": ok, "detail": _err(c["schemaAndSignatureCheck"].get("error"))})
            invalid |= not ok
        if c.get("expiryCheck") is not None:
            ok = bool(c["expiryCheck"].get("valid"))
            checks.append({"label": "Not expired" + n, "ok": ok, "detail": None})
            expired |= not ok
        for s in c.get("statusCheck") or []:
            ok = bool(s.get("valid"))
            checks.append({"label": f"Status ({s.get('purpose')})" + n, "ok": ok, "detail": _err(s.get("error"))})
            invalid |= not ok
        claims.update(c.get("claims") or {})
    status = "INVALID" if invalid else "EXPIRED" if expired else "VALID" if b.get("allChecksSuccessful") else "INVALID"
    first_fail = next((c for c in checks if not c["ok"]), None)
    detail = f"{first_fail['label']} failed" + (f": {first_fail['detail']}" if first_fail and first_fail["detail"] else "") if first_fail else None
    return {"status": status, "detail": detail, "checks": checks, "claims": claims, "raw": b,
            "credentials": [c.get("verifiableCredential") for c in creds]}


def map_v1(b: dict) -> dict:
    """VPTokenResultDto -> VALID / INVALID / EXPIRED."""
    results = (b or {}).get("vcResults") or []
    statuses = [v.get("verificationStatus") for v in results]
    status = "VALID" if b.get("vpResultStatus") == "SUCCESS" else "INVALID"
    if "EXPIRED" in statuses and not any(s in ("INVALID", "REVOKED") for s in statuses):
        status = "EXPIRED"
    checks = [{"label": f"Credential {i + 1}", "ok": s == "SUCCESS", "detail": s} for i, s in enumerate(statuses)]
    return {"status": status, "detail": ("vcResults: " + ", ".join(map(str, statuses))) if statuses else None,
            "checks": checks, "claims": {}, "raw": b, "credentials": [v.get("vc") for v in results]}
