"""
JSON-LD Linked Data proofs, the two kinds this component needs:

- JsonWebSignature2020 (ES256 or EdDSA): what the wallet signs a JSON-LD
  presentation with. Inji Verify 0.18.2 (vc-verifier 1.8.1) can check this
  proof type on a presentation; it cannot check RsaSignature2018, even though
  it advertises it (see docs/FINDINGS.md, F8).
- Ed25519Signature2020: what Inji Certify signs the credential with. We only
  verify it here (independent check), and sign it in tests with a test issuer.

Both use the same "verify data" as Inji's vc-verifier (ld-signatures-java
URDNA2015Canonicalizer) and Digital Bazaar's jsonld-signatures:

    SHA-256(URDNA2015(proof options + document @context)) || SHA-256(URDNA2015(document without proof))

JsonWebSignature2020 then signs that as a detached, unencoded-payload JWS
(RFC 7797): ASCII(b64url(header)) + "." + verify_data, header
{"alg": ..., "b64": false, "crit": ["b64"]}, serialized as "<header>..<signature>".
"""
import base64
import hashlib
import json
import logging
import os
from datetime import datetime, timezone

import requests
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature
from pyld import jsonld

logger = logging.getLogger(__name__)

CREDENTIALS_V1 = "https://www.w3.org/2018/credentials/v1"
JWS_2020_CONTEXT = "https://w3id.org/security/suites/jws-2020/v1"
ED25519_2020_CONTEXT = "https://w3id.org/security/suites/ed25519-2020/v1"

_CONTEXT_DIR = os.path.join(os.path.dirname(__file__), "contexts")
with open(os.path.join(_CONTEXT_DIR, "index.json")) as f:
    _BUNDLED = {url: os.path.join(_CONTEXT_DIR, name) for url, name in json.load(f).items()}
_cache = {}
REMOTE_CONTEXTS = os.environ.get("ALLOW_REMOTE_CONTEXTS", "1") != "0"


def document_loader(url, options=None):
    """Bundled contexts first (works offline, and can't be swapped under us),
    then the network with a cache, like Inji's own ConfigurableDocumentLoader."""
    if url in _cache:
        doc = _cache[url]
    elif url in _BUNDLED:
        with open(_BUNDLED[url]) as f:
            doc = _cache[url] = json.load(f)
    elif REMOTE_CONTEXTS:
        r = requests.get(url, headers={"Accept": "application/ld+json, application/json"}, timeout=15)
        r.raise_for_status()
        doc = _cache[url] = r.json()
    else:
        raise ValueError(f"JSON-LD context {url} is not bundled and remote loading is off")
    return {"contextUrl": None, "documentUrl": url, "document": doc}


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def canonize(doc: dict) -> str:
    return jsonld.normalize(doc, {"algorithm": "URDNA2015", "format": "application/n-quads", "documentLoader": document_loader})


def verify_data(document: dict, proof: dict) -> bytes:
    doc = {k: v for k, v in document.items() if k != "proof"}
    options = {k: v for k, v in proof.items() if k not in ("jws", "proofValue", "signatureValue")}
    options["@context"] = doc["@context"]
    return hashlib.sha256(canonize(options).encode()).digest() + hashlib.sha256(canonize(doc).encode()).digest()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _with_context(document: dict, ctx_url: str) -> dict:
    ctx = document["@context"] if isinstance(document["@context"], list) else [document["@context"]]
    doc = dict(document)
    doc["@context"] = ctx if ctx_url in ctx else ctx + [ctx_url]
    doc.pop("proof", None)
    return doc


def _proof_options(proof_type, verification_method, purpose, challenge=None, domain=None, created=None):
    proof = {"type": proof_type, "created": created or now_iso(), "verificationMethod": verification_method, "proofPurpose": purpose}
    if challenge is not None:
        proof["challenge"] = challenge
    if domain is not None:
        proof["domain"] = domain
    return proof


# ------------------------------------------------------- JsonWebSignature2020

def sign_jws2020(document: dict, private_key, verification_method: str, purpose: str,
                 challenge: str = None, domain: str = None, created: str = None) -> dict:
    """Sign with an EC P-256 key (ES256) or an Ed25519 key (EdDSA)."""
    if isinstance(private_key, ec.EllipticCurvePrivateKey):
        alg = "ES256"
    elif isinstance(private_key, ed25519.Ed25519PrivateKey):
        alg = "EdDSA"
    else:
        raise ValueError("JsonWebSignature2020 here supports EC P-256 and Ed25519 keys only")
    doc = _with_context(document, JWS_2020_CONTEXT)
    proof = _proof_options("JsonWebSignature2020", verification_method, purpose, challenge, domain, created)
    header_b64 = b64url(json.dumps({"alg": alg, "b64": False, "crit": ["b64"]}, separators=(",", ":")).encode())
    signing_input = header_b64.encode("ascii") + b"." + verify_data(doc, proof)
    if alg == "ES256":
        r, s = decode_dss_signature(private_key.sign(signing_input, ec.ECDSA(hashes.SHA256())))
        signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    else:
        signature = private_key.sign(signing_input)
    proof["jws"] = f"{header_b64}..{b64url(signature)}"
    doc["proof"] = proof
    return doc


def verify_jws2020(document: dict, public_key) -> bool:
    proof = document.get("proof") or {}
    if proof.get("type") != "JsonWebSignature2020" or "jws" not in proof:
        return False
    try:
        header_b64, payload, sig_b64 = proof["jws"].split(".")
        if payload:
            return False  # must be detached
        header = json.loads(b64url_decode(header_b64))
        signing_input = header_b64.encode("ascii") + b"." + verify_data(document, proof)
        sig = b64url_decode(sig_b64)
        if header.get("alg") == "ES256":
            if len(sig) != 64:
                return False
            der = encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big"))
            public_key.verify(der, signing_input, ec.ECDSA(hashes.SHA256()))
        elif header.get("alg") == "EdDSA":
            public_key.verify(sig, signing_input)
        else:
            return False
        return True
    except (InvalidSignature, ValueError, TypeError, AttributeError):
        return False
    except Exception:
        logger.exception("unexpected error verifying JsonWebSignature2020")
        return False


# -------------------------------------------------------- Ed25519Signature2020

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = _B58[r] + out
    return "1" * (len(data) - len(data.lstrip(b"\0"))) + out


def b58decode(s: str) -> bytes:
    n = 0
    for c in s:
        n = n * 58 + _B58.index(c)
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + body


def sign_ed25519_2020(document: dict, private_key: ed25519.Ed25519PrivateKey, verification_method: str,
                      purpose: str = "assertionMethod", challenge=None, domain=None, created=None) -> dict:
    doc = _with_context(document, ED25519_2020_CONTEXT)
    proof = _proof_options("Ed25519Signature2020", verification_method, purpose, challenge, domain, created)
    proof["proofValue"] = "z" + b58encode(private_key.sign(verify_data(doc, proof)))
    doc["proof"] = proof
    return doc


def verify_ed25519_2020(document: dict, public_key) -> bool:
    proof = document.get("proof") or {}
    value = proof.get("proofValue", "")
    if proof.get("type") != "Ed25519Signature2020" or not value.startswith("z"):
        return False
    try:
        public_key.verify(b58decode(value[1:]), verify_data(document, proof))
        return True
    except (InvalidSignature, ValueError, TypeError, AttributeError):
        return False
    except Exception:
        logger.exception("unexpected error verifying Ed25519Signature2020")
        return False
