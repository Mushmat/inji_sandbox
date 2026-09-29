"""
Public keys from DIDs, for the methods this stack uses:

  did:jwk  - holder keys (Certify writes did:jwk into credentialSubject.id / cnf.kid)
  did:key  - Ed25519 (z6Mk...) and P-256 (zDn...)
  did:web  - Certify's issuer DID, e.g. did:web:mushmat.github.io:inji-did
"""
import json
import os

import requests
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from jwt.algorithms import ECAlgorithm, OKPAlgorithm, RSAAlgorithm

from jsonld_proofs import b58decode, b64url, b64url_decode

REQUEST_TIMEOUT = 15


def default_fetch_json(url: str) -> dict:
    r = requests.get(url, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()


def jwk_to_public_key(jwk: dict):
    kty = jwk.get("kty")
    data = json.dumps(jwk)
    if kty == "EC":
        return ECAlgorithm.from_jwk(data)
    if kty == "OKP":
        return OKPAlgorithm.from_jwk(data)
    if kty == "RSA":
        return RSAAlgorithm.from_jwk(data)
    raise ValueError(f"unsupported JWK kty {kty!r}")


def public_key_to_jwk(public_key) -> dict:
    if isinstance(public_key, ec.EllipticCurvePublicKey):
        return json.loads(ECAlgorithm.to_jwk(public_key))
    if isinstance(public_key, ed25519.Ed25519PublicKey):
        return json.loads(OKPAlgorithm.to_jwk(public_key))
    return json.loads(RSAAlgorithm.to_jwk(public_key))


def did_jwk(public_key) -> str:
    jwk = {k: v for k, v in public_key_to_jwk(public_key).items() if k in ("kty", "crv", "x", "y", "n", "e")}
    return "did:jwk:" + b64url(json.dumps(jwk, separators=(",", ":")).encode())


def jwk_of_did(did_or_vm: str):
    """Public JWK for did:jwk / did:key, None for anything else."""
    if not did_or_vm:
        return None
    did = did_or_vm.split("#")[0]
    try:
        if did.startswith("did:jwk:"):
            return json.loads(b64url_decode(did[len("did:jwk:"):]))
        if did.startswith("did:key:"):
            return public_key_to_jwk(_multibase_key(did[len("did:key:"):]))
    except Exception:
        return None
    return None


def same_key(jwk_a, jwk_b) -> bool:
    if not jwk_a or not jwk_b:
        return False
    fields = ("kty", "crv", "x", "y", "n", "e")
    return all(jwk_a.get(f) == jwk_b.get(f) for f in fields)


def _multibase_key(mb: str):
    if not mb.startswith("z"):
        raise ValueError("only base58btc multibase keys are supported")
    raw = b58decode(mb[1:])
    if raw[:2] == b"\xed\x01":
        return ed25519.Ed25519PublicKey.from_public_bytes(raw[2:])
    if raw[:2] == b"\x80\x24":  # p256-pub, compressed point
        return ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), raw[2:])
    if len(raw) == 32:  # bare Ed25519 key (older DID documents)
        return ed25519.Ed25519PublicKey.from_public_bytes(raw)
    raise ValueError("unsupported multicodec key type")


def _vm_key(vm: dict):
    try:
        if "publicKeyJwk" in vm:
            return jwk_to_public_key(vm["publicKeyJwk"])
        if "publicKeyMultibase" in vm:
            return _multibase_key(vm["publicKeyMultibase"])
    except ValueError:
        return None
    return None


def did_document_keys(doc: dict) -> dict:
    """{verification method id: public JWK} for comparing two copies of a DID document."""
    out = {}
    for vm in doc.get("verificationMethod", []):
        key = _vm_key(vm)
        if key is not None:
            out[vm.get("id")] = public_key_to_jwk(key)
    return out


def did_web_url(did: str) -> str:
    parts = [requests.utils.unquote(p) for p in did[len("did:web:"):].split(":")]
    host, path = parts[0], parts[1:]
    return f"https://{host}/{'/'.join(path)}/did.json" if path else f"https://{host}/.well-known/did.json"


def did_web_overrides() -> dict:
    """DID_WEB_OVERRIDES="did:web:a=http://localhost:8090/v1/certify/.well-known/did.json,..."
    lets a local run use Certify's own DID document before it is published."""
    out = {}
    for item in filter(None, os.environ.get("DID_WEB_OVERRIDES", "").split(",")):
        did, _, url = item.partition("=")
        out[did.strip()] = url.strip()
    return out


_KEY_TYPES = {"EdDSA": ed25519.Ed25519PublicKey, "ES256": ec.EllipticCurvePublicKey}


def resolve_key(verification_method: str, fetch_json=default_fetch_json, alg: str = None):
    """Returns (public_key, info). info has method, did, and fetched_from for did:web.
    alg (e.g. "EdDSA") picks the matching key when the DID document has several
    and the reference has no #fragment."""
    did = verification_method.split("#")[0]
    if did.startswith("did:jwk:"):
        return jwk_to_public_key(jwk_of_did(did)), {"method": "jwk", "did": did}
    if did.startswith("did:key:"):
        return _multibase_key(did[len("did:key:"):]), {"method": "key", "did": did}
    if did.startswith("did:web:"):
        url = did_web_overrides().get(did) or did_web_url(did)
        doc = fetch_json(url)
        fragment = verification_method.split("#", 1)[1] if "#" in verification_method else None
        vms = doc.get("verificationMethod", [])
        vm = next((v for v in vms if v.get("id") == verification_method or (fragment and v.get("id", "").endswith("#" + fragment))), None)
        if vm is None and not fragment:
            candidates = [(v, _vm_key(v)) for v in vms]
            wanted = _KEY_TYPES.get(alg)
            vm = next((v for v, k in candidates if k is not None and (wanted is None or isinstance(k, wanted))), None)
        if vm is None:
            raise ValueError(f"{verification_method} not found in the DID document at {url}")
        key = _vm_key(vm)
        if key is None:
            raise ValueError(f"verification method {vm.get('id')} has no supported key encoding")
        return key, {"method": "web", "did": did, "fetched_from": url, "verification_method": vm.get("id")}
    raise ValueError(f"unsupported DID method in {verification_method}")
