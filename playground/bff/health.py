"""Is each module up, and does Certify still sign with the key the world can see?"""

import os
from concurrent.futures import ThreadPoolExecutor

import requests

from config import CERTIFY_URL, INJI_VERIFY_URL, INJI_WEB_URL, MIMOTO_URL, PUBLISHED_DID_URL

SERVICES = [
    # (id, label, url, statuses that mean "up")
    ("certify", "Inji Certify", f"{CERTIFY_URL}/.well-known/openid-credential-issuer", {200}),
    ("inji_verify", "Inji Verify", f"{INJI_VERIFY_URL}/vp-request/x/status", {404}),
    ("mimoto", "Mimoto", f"{MIMOTO_URL}/issuers", {200}),
    ("inji_web", "Inji Web", INJI_WEB_URL, {200}),
]


def _probe(service):
    sid, label, url, ok = service
    try:
        code = requests.get(url, timeout=4).status_code
        return {"id": sid, "label": label, "url": url, "up": code in ok, "detail": f"HTTP {code}"}
    except requests.RequestException as e:
        return {"id": sid, "label": label, "url": url, "up": False, "detail": type(e).__name__}


def _did_keys(url):
    try:
        doc = requests.get(url, timeout=6).json()
        return {vm.get("publicKeyMultibase") for vm in doc.get("verificationMethod", [])}
    except (requests.RequestException, ValueError):
        return set()


def status() -> dict:
    with ThreadPoolExecutor(max_workers=len(SERVICES) + 2) as pool:
        probes = list(pool.map(_probe, SERVICES))
        live = pool.submit(_did_keys, f"{CERTIFY_URL}/.well-known/did.json")
        published = pool.submit(_did_keys, PUBLISHED_DID_URL)
        live, published = live.result(), published.result()

    tunnel = next((pair.split("=", 1)[0] for pair in os.environ.get("WALLET_URL_REWRITES", "").split(",") if "=" in pair), None)
    if tunnel:
        probes.append(_probe(("tunnel", "https tunnel", f"{tunnel}/v1/verify/vp-request/x/status", {404})))

    if not live:
        did = {"ok": False, "detail": "Certify isn't answering, so its keys can't be compared."}
    elif not published:
        did = {"ok": False, "detail": f"Couldn't fetch the published DID document at {PUBLISHED_DID_URL}."}
    elif live == published:
        did = {"ok": True, "detail": "Certify signs with the keys published at " + PUBLISHED_DID_URL}
    else:
        did = {"ok": False, "detail": "Certify's keys don't match the published DID document, so verifiers will reject "
                                      "its credentials. See certify/README.md, 'Running this issuer on another machine'."}
    return {"services": probes, "did": did}
