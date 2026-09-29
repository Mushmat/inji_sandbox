"""
SD-JWT VC handling for the wallet (present with a key-binding JWT) and for
the independent checks (parse, recover disclosed claims, verify).

Handles nested disclosures, which Certify produces: with
sdClaim "$.credentialSubject.farmerID" the digest sits in
payload.credentialSubject._sd, not at the top level.
"""
import hashlib
import json
import time

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

from jsonld_proofs import b64url, b64url_decode


def digest(encoded_disclosure: str) -> str:
    return b64url(hashlib.sha256(encoded_disclosure.encode("ascii")).digest())


def make_disclosure(name: str, value, salt: str) -> str:
    return b64url(json.dumps([salt, name, value]).encode())


def decode_disclosure(encoded: str) -> dict:
    arr = json.loads(b64url_decode(encoded))
    d = {"encoded": encoded, "digest": digest(encoded), "salt": arr[0]}
    if len(arr) == 3:
        d["name"], d["value"] = arr[1], arr[2]
    else:  # array element disclosure
        d["name"], d["value"] = None, arr[1]
    return d


def decode_jwt_part(part: str) -> dict:
    return json.loads(b64url_decode(part))


def parse(compact: str) -> dict:
    parts = compact.split("~")
    last = parts[-1]
    kb = last if last.count(".") == 2 else None
    middle = [p for p in (parts[1:-1] if kb else parts[1:]) if p]
    header_b64, payload_b64, _ = parts[0].split(".")
    presented_part = compact[: len(compact) - len(kb)] if kb else (compact if compact.endswith("~") else compact + "~")
    return {
        "jwt": parts[0],
        "header": decode_jwt_part(header_b64),
        "payload": decode_jwt_part(payload_b64),
        "disclosures": [decode_disclosure(d) for d in middle],
        "kb_jwt": kb,
        "presented_part": presented_part,
    }


def reconstruct(payload: dict, disclosures: list):
    """Replace _sd digests with the disclosed claims, recursively.
    Returns (view, unmatched_disclosures, paths_of_disclosed_claims)."""
    by_digest = {d["digest"]: d for d in disclosures}
    used, paths = set(), {}

    def walk(node, path):
        if isinstance(node, dict):
            out = {}
            for k, v in node.items():
                if k in ("_sd", "_sd_alg"):
                    continue
                out[k] = walk(v, f"{path}.{k}")
            for dg in node.get("_sd", []):
                d = by_digest.get(dg)
                if d and d["name"] is not None:
                    used.add(dg)
                    out[d["name"]] = walk(d["value"], f"{path}.{d['name']}")
                    paths[d["name"]] = f"{path}.{d['name']}"
            return out
        if isinstance(node, list):
            out = []
            for item in node:
                if isinstance(item, dict) and set(item) == {"..."}:
                    d = by_digest.get(item["..."])
                    if d:
                        used.add(item["..."])
                        out.append(walk(d["value"], path))
                else:
                    out.append(walk(item, path))
            return out
        return node

    view = walk(payload, "$")
    unmatched = [d for d in disclosures if d["digest"] not in used]
    return view, unmatched, paths


def _alg_for(key) -> str:
    if isinstance(key, ec.EllipticCurvePrivateKey):
        return "ES256"
    if isinstance(key, ed25519.Ed25519PrivateKey):
        return "EdDSA"
    return "RS256"


def present(compact: str, disclose, holder_key, audience: str, nonce: str, mutate=None) -> dict:
    """disclose(name) -> bool picks disclosures to reveal; mutate(disclosure) may
    rewrite one (tamper tests). Appends a KB-JWT per SD-JWT spec."""
    p = parse(compact)
    chosen = [d for d in p["disclosures"] if d["name"] is None or disclose(d["name"])]
    withheld = [d["name"] for d in p["disclosures"] if d not in chosen]
    if mutate:
        chosen = [mutate(d) for d in chosen]
    presented = p["jwt"] + "~" + "".join(d["encoded"] + "~" for d in chosen)
    kb_header = {"typ": "kb+jwt", "alg": _alg_for(holder_key)}
    kb_payload = {"iat": int(time.time()), "aud": audience, "nonce": nonce,
                  "sd_hash": b64url(hashlib.sha256(presented.encode("ascii")).digest())}
    kb = pyjwt.encode(kb_payload, holder_key, algorithm=kb_header["alg"], headers={"typ": "kb+jwt"})
    return {"presentation": presented + kb, "kb_header": kb_header, "kb_payload": kb_payload,
            "disclosed": [{d["name"]: d["value"]} for d in chosen], "withheld": withheld}


def verify_jws(compact_jwt: str, public_key) -> bool:
    try:
        alg = decode_jwt_part(compact_jwt.split(".")[0]).get("alg")
        pyjwt.decode(compact_jwt, public_key, algorithms=[alg], options={"verify_aud": False, "verify_exp": False, "verify_iat": False, "verify_nbf": False, "require": []})
        return True
    except Exception:
        return False
