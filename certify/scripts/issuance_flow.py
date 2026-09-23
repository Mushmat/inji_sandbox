"""
Core OpenID4VCI issuance flow logic, shared by test_issuance_flow.py (the
CLI smoke test) and demo-ui/server.py (the toy UI backend). One copy of the
flow, two ways to run it.

Talks to MOSIP Collab's public mock eSignet for login, then requests a
credential from a local Certify instance (see ../docker-compose/).
"""
import json
import logging
import time
import uuid
import base64
import secrets
import hashlib

import requests
import jwt as pyjwt
from jwt.algorithms import RSAAlgorithm
from cryptography.hazmat.primitives.asymmetric import rsa

logger = logging.getLogger(__name__)

AUTH_SERVER = "https://esignet-mock.collab.mosip.net/v1/esignet"
CERTIFY_URL = "http://localhost:8090/v1/certify"
CLIENT_ID = "wallet-demo"
REDIRECT_URI = "http://localhost:3004/redirect"
INDIVIDUAL_ID = "2154189532"
AUD_URL = "http://certify-nginx:80"   # has to match mosip_certify_domain_url in docker-compose.yaml
SCOPE = "mock_identity_vc_ldp"        # only scope wallet-demo has on Collab, both formats share it
VALID_FORMATS = ("ldp_vc", "vc+sd-jwt")
REQUEST_TIMEOUT = 15  # seconds, applied to every call out to eSignet or Certify

# Demo client key MOSIP publishes in their own repo for testing against Collab.
# Not a secret, it's meant to be used like this.
PRIVATE_KEY_JWK = {
    "kty": "RSA",
    "n": "r4uINbmHn6cF70WcrCCKHZY5K2_3TrnnltgjUref6x3I5fHUJDAbVEyAKeroaivgPiGdWrzlke3Or_u7aNefQ0MSodlWWWF6gxxq25pTjmRquglGj8hsfLe5sY61mN9K-x_u62jgvrYKdoQMZO5EYOxga6mVfTu03J6uS0ej5JtwedJb5WvQkfl0P5u-ld77r9PyTUhn9HOAh_3k1vAZeXzv5ae7wz47gvAReWl-N_dds3wqrdF0VZkaAdvU4K4yYHxqV2AzBpW_O6TTaHVdSPjvBnbHGPJwB12qllbhDOn4nvRzaxy9i9dpJtgLnVVPygtGJ7YggmBD-uv16oGxw8_1mAwLowA0fDc-TttNAfAPTe6W9_28yxRGyFTX4WaEVw9vqDBd7Pd4rdB_Bk_KFzBVDQKj3AFB1swWAGfPssferbWsPdMAACAO4x9LZGimCyRjbL04CQZYXC18o-VFTBKeB23n80ZDIYJ2oABO_qXCAA4CyEX-JOKh4nU1piDPVz_yAgPBBWPnZhaOUm6oonw1apuwg191zgUNlME-vNdOYov1wSUNAoHa5hlKoLAkMvL9oxhHIpuruH3x2NEjhtgDgh-IcqK3GNnr0eJ_ySNKJSebTQ8u_BVOsNeoXHcPkD-dIAz6CYg-ehSavwq8OeKtETF48UWkEZh4PEr6q9k",
    "e": "AQAB",
    "d": "Sr4eQMG9_TwgSsBY9PDl3bMYpGYH5n1BHfjpEU8dx_3mjAFrUf0ppbrs1uwuCQalc87cMMY8-OVIG6YTJZCpPvpP9JmVKnlWsHxpAxeye-5FgvBwGsg7aN7RMciRiYWJZ2MxVwpQpuLbkZqnrFHGy33Zj_2kqK3DVCw8CdF29t84BKaMeiJtq7mKxYqKm0VV5IdZo44wtOR41W5FAT85mYCYpC_Gwlq8_AM7bXZ9R1cLjmBPy7Ji1g9aA3CWMxP4XxyaKpnLIAKiacLEQLW4Aln7a8UnAHg5OummuFxFdjoooYVznyedjO0q2F8kktjAIEasmDvzm49hYnUVP8P467H8Zuk4v4GQYpx9JZXo_2CNvfbDJvxHyQmm5RPHlw4nsMr6pcIdAecQP9-kwpWTajuGf5l2hYL231eMLIS-qOSCnsYHijbO-684Xfd9pRBHqam9oOaBLlO_gcp-AoqKNeE-y2v0rrpq9vG8pWtVX-mJpZowm93t7ShqggV2M84U--BKbz3Wj9_6UWGZ4zcU-aimXUmDefvchEgEIiovZUMD_HqDkwFQciIMBZHlxMRcyo4dXqikavM-6JeJ3242stZvyLJaYXTOhLE6Qj_VO3GZIlxHV8VYkeoEGmeqFE66sfrYuAETUjLaSiH57O-W2KyxvFmp7BfD0OuUBT2aJAE",
    "p": "27x7D8bOOuy37BTELXS7ieF7IeL8mJCzkGsMG_6EeIUj-tEG04nqzpJs4yZfQMqN_AYwnuiKA6IHtjAwJW9TVe-xY8zAqTPB61tWuPk3fKqXvXBRnXLkcGr0rXa5EaGzAiTbUmOA4bJ56bnsB63Vw_od3Kva1XFoTx3fpsWsPqR8dVkHfbJ9TSNJek3JgHovbFbPeNt5wrCJBhVx2njb8p_bwYAolJTp4MH6OxFycJ3K2Pj3swRGeQpKBqQvs4nSPTeEEJTGtwR6UGW1rdkNqvlgzuctUnAWuj_m2lZLsKJUMQ2mY5X-lZSUWEnz-KkrSsqI3B8aYc6vLLfzmpllLw",
    "q": "zIQKcDw8v9mjAE1W1aM8VHGnTwqbsakbdxab-jNkXPsZXjPocC3Oc-OMOxoZmyBrH09-JsIU_HutfEAyvwtnV7MQynnDDMvHnelyIDI1A6UxxkurO6QSMRpq7mkG7of_av_O8dQOJOqfs0Xik6-8RKD-DCUcR1vmpYAZQ_CgAmFeaaiwd1MaYKd5tkbzDMkC796NMTXi3b0MSzjsdUpvHBVIkOrnMsk9KCj_jo9I3uxvV02nOvUs8hmLB94vD04_DY_RHxIFncDFSrUykmF9wYVti2dQ8SVvUEl2zIukzewNxHsLoHrD2GuvwGNyB3iPJeGRn5GRAMB18wuURTrNdw",
    "dp": "WlAFZF6ZtK5GicmfN--ahPkf2rWojCwtIVZeC8N4PvC58QSogZlV4MFd75591-tooAULRsTctNGLyd3UbA5tegyiJBqrtN-I_Gr2IeCMZbjX1Qys_sGSEoJjPkhlmFGVeXQckKhE-H6ajO3VjPJtwbazP1eDAecysBHfMnRcbwK8BJ8q7QbHaUTvlk0SXLPbefPUIiBS0yorp0x5FwpFnFsHv2glRaxO1AnmBxEMsCyqirMJW5KORIFuG3yv_mLO_korBYWghuhYPWMQYPutGnCU0XVCs3dOYA6Tm3mMcnTFlcO-d3_WuzPuJLuAgttE5-CGj7JY7Yo9hWu1u_0AEQ",
    "dq": "r1tUG_H6YMF6Wur1Vo71Tq54t3QwFUAbdZvkN77TAkqm8LfvSChuib2E4rQ5WmKMlzcwwojNN8PP9-aP3HEpte-qqQGINbOQwByHJ4YFINAHArCk7Kl8k6_EGhHhyKrBXXxjc8TQL-Ug87UrVlhrRCkKS12ShrkM5cEVaMSsXf4g1tW2IUoXJuLSoHDrO34rT4Lya0x57oiHPwRa8yLUbC7vnppbjJcyIfotTY4b_FCcEy5ZAltwo1E1fZSLo0MDG1zCATMRr7a3M5xz9UE0c7c1Oz9mDq57aErlWvMtZwdMsriSOpKo1CtZccuS3UcI7oEfvMMyooNjXvcBte56dw",
    "qi": "yFkQxMJr9omhM2hNSrXsg0jEykUHxQ56wWt1FvWtaPJVDuygazI1J5Ga_YcL2Yu7gDgukTUblDkgqkYr9Q8GrbmgbBiTj7WW2q7GqnTRoiMkwoPGUjgQJGDYjDleVMNByn_UHGnyctYWC59FceAgvQ7f2CwnIe1HehfGiXt3AxDMddnAva28WJ0rtnGwAKMoyMfo2f3fij50leoHn_0Rkpqbw_suVP7PNZxj_7Ul7-kA9jTDyHbb3pTR1yNyv85XU6xwnQeY8YOkGZt9xlJ3xY6A3mVuLTEhUmROJ-UwOZAZNZ8rUFA2mc7Jjl9aQd4A3A_PWw7Cg6l6LIUDvi4f8Q",
}


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def pkce_pair():
    verifier = b64url(secrets.token_bytes(32))
    challenge = b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def decode_jwt_part(part: str) -> dict:
    padded = part + "=" * (-len(part) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def run_issuance(vc_format: str) -> dict:
    """Runs the full flow and returns a dict with every step taken, plus the
    result. Never raises - a bad format, a network drop, or Collab being down
    all come back as a normal {"ok": False, "error": ...} result instead of
    an exception, so callers (CLI or web) never have to guard this in a
    try/except of their own."""
    if vc_format not in VALID_FORMATS:
        return {
            "format": vc_format,
            "steps": [],
            "ok": False,
            "error": f"unknown format {vc_format!r}, expected one of {VALID_FORMATS}",
            "credential": None,
        }

    steps = []

    try:
        return _run_issuance(vc_format, steps)
    except requests.exceptions.RequestException as e:
        logger.exception("network error during issuance flow")
        return {"format": vc_format, "steps": steps, "ok": False, "error": f"network error: {e}", "credential": None}
    except (KeyError, ValueError, IndexError) as e:
        logger.exception("unexpected response shape during issuance flow")
        return {"format": vc_format, "steps": steps, "ok": False, "error": f"unexpected response: {e}", "credential": None}


def _run_issuance(vc_format: str, steps: list) -> dict:
    session = requests.Session()

    def record(name, method, url, resp, extra=None):
        entry = {
            "name": name,
            "method": method,
            "url": url,
            "status": resp.status_code,
            "ok": resp.status_code == 200,
        }
        if extra:
            entry.update(extra)
        try:
            entry["response"] = resp.json()
        except ValueError:
            entry["response"] = resp.text[:500]
        steps.append(entry)
        return entry["ok"]

    def fail(msg):
        return {"format": vc_format, "steps": steps, "ok": False, "error": msg, "credential": None}

    # 1. CSRF token
    r = session.get(f"{AUTH_SERVER}/csrf/token", timeout=REQUEST_TIMEOUT)
    record("Get CSRF token", "GET", f"{AUTH_SERVER}/csrf/token", r)
    csrf = session.cookies.get("XSRF-TOKEN")

    # 2. PKCE pair for the auth-code exchange
    verifier, challenge = pkce_pair()

    # 3. oauth-details - starts the login transaction
    body = {
        "requestTime": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "request": {
            "clientId": CLIENT_ID,
            "scope": SCOPE,
            "responseType": "code",
            "redirectUri": REDIRECT_URI,
            "display": "popup",
            "prompt": "login",
            "acrValues": "mosip:idp:acr:generated-code",
            "nonce": uuid.uuid4().hex,
            "state": "eree2311",
            "claimsLocales": "en",
            "codeChallenge": challenge,
            "codeChallengeMethod": "S256",
        },
    }
    r = session.post(f"{AUTH_SERVER}/authorization/v2/oauth-details",
                      json=body, headers={"X-XSRF-TOKEN": csrf}, timeout=REQUEST_TIMEOUT)
    if not record("Start authorization (oauth-details)", "POST",
                   f"{AUTH_SERVER}/authorization/v2/oauth-details", r):
        return fail("oauth-details failed")
    resp_json = r.json()
    transaction_id = resp_json["response"]["transactionId"]
    # hash the response exactly as the server sent it (same key order) or the
    # server-side check on the next call won't match
    compact = json.dumps(resp_json["response"], separators=(",", ":"))
    oauth_details_hash = b64url(hashlib.sha256(compact.encode()).digest())
    csrf = session.cookies.get("XSRF-TOKEN") or csrf

    auth_headers = {
        "X-XSRF-TOKEN": csrf,
        "oauth-details-key": transaction_id,
        "oauth-details-hash": oauth_details_hash,
    }

    # 4. send-otp - mock IDP's OTP is always 111111
    body = {
        "requestTime": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "request": {
            "transactionId": transaction_id,
            "individualId": INDIVIDUAL_ID,
            "otpChannels": ["email", "phone"],
            "captchaToken": "dummy",
        },
    }
    r = session.post(f"{AUTH_SERVER}/authorization/send-otp", json=body, headers=auth_headers, timeout=REQUEST_TIMEOUT)
    if not record("Send OTP", "POST", f"{AUTH_SERVER}/authorization/send-otp", r):
        return fail("send-otp failed")

    # 5. authenticate with the mock OTP
    csrf = session.cookies.get("XSRF-TOKEN") or csrf
    auth_headers["X-XSRF-TOKEN"] = csrf
    body = {
        "requestTime": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "request": {
            "transactionId": transaction_id,
            "individualId": INDIVIDUAL_ID,
            "challengeList": [{"authFactorType": "OTP", "challenge": "111111", "format": "alpha-numeric"}],
        },
    }
    r = session.post(f"{AUTH_SERVER}/authorization/v3/authenticate", json=body, headers=auth_headers, timeout=REQUEST_TIMEOUT)
    if not record("Authenticate (OTP)", "POST", f"{AUTH_SERVER}/authorization/v3/authenticate", r):
        return fail("authenticate failed")

    # 6. auth-code
    csrf = session.cookies.get("XSRF-TOKEN") or csrf
    auth_headers["X-XSRF-TOKEN"] = csrf
    body = {
        "requestTime": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "request": {"transactionId": transaction_id, "acceptedClaims": [], "permittedAuthorizeScopes": [SCOPE]},
    }
    r = session.post(f"{AUTH_SERVER}/authorization/auth-code", json=body, headers=auth_headers, timeout=REQUEST_TIMEOUT)
    if not record("Get authorization code", "POST", f"{AUTH_SERVER}/authorization/auth-code", r):
        return fail("auth-code failed")
    code = r.json()["response"]["code"]

    # 7. token exchange - client_assertion JWT signed with wallet-demo's private key
    token_endpoint = f"{AUTH_SERVER}/oauth/v2/token"
    client_assertion = pyjwt.encode(
        {
            "iss": CLIENT_ID,
            "sub": CLIENT_ID,
            "aud": token_endpoint,
            "jti": uuid.uuid4().hex,
            "iat": int(time.time()),
            "exp": int(time.time()) + 60,
        },
        RSAAlgorithm.from_jwk(json.dumps(PRIVATE_KEY_JWK)),
        algorithm="RS256",
    )
    form = {
        "code": code,
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
        "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
        "client_assertion": client_assertion,
        "code_verifier": verifier,
    }
    r = session.post(token_endpoint, data=form, timeout=REQUEST_TIMEOUT)
    if not record("Exchange code for access token", "POST", token_endpoint, r):
        return fail("token exchange failed")
    tok = r.json()
    access_token = tok["access_token"]
    c_nonce = tok.get("c_nonce")

    # 8. build the holder proof JWT - a fresh keypair per request, per spec
    holder_priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    holder_pub_jwk = json.loads(RSAAlgorithm.to_jwk(holder_priv.public_key()))
    holder_pub_jwk["alg"] = "RS256"
    holder_pub_jwk["use"] = "sig"

    now = int(time.time())
    proof_jwt = pyjwt.encode(
        {"aud": AUD_URL, "nonce": c_nonce, "iss": CLIENT_ID, "iat": now, "exp": now + 600},
        holder_priv,
        algorithm="RS256",
        headers={"typ": "openid4vci-proof+jwt", "jwk": holder_pub_jwk},
    )

    # 9. request the credential
    cred_body = {"format": vc_format}
    if vc_format == "ldp_vc":
        cred_body["credential_definition"] = {
            "type": ["VerifiableCredential", "FarmerCredential"],
            "@context": ["https://www.w3.org/2018/credentials/v1"],
        }
    else:
        cred_body["vct"] = "FarmerCredentialSdJwt"
    cred_body["proof"] = {"proof_type": "jwt", "jwt": proof_jwt}

    r = requests.post(
        f"{CERTIFY_URL}/issuance/credential",
        json=cred_body,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=REQUEST_TIMEOUT,
    )
    if not record("Request the credential", "POST", f"{CERTIFY_URL}/issuance/credential", r):
        return fail("credential request failed")

    credential = r.json()["credential"]
    decoded = None
    if vc_format != "ldp_vc" and isinstance(credential, str):
        jwt_part, *disclosure_parts = credential.split("~")
        header_b64, payload_b64, _sig = jwt_part.split(".")
        decoded = {
            "header": decode_jwt_part(header_b64),
            "payload": decode_jwt_part(payload_b64),
            "disclosures": [decode_jwt_part(d) for d in disclosure_parts if d],
        }

    return {
        "format": vc_format,
        "steps": steps,
        "ok": True,
        "error": None,
        "credential": credential,
        "credential_decoded": decoded,
    }
