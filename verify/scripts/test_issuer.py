"""
An offline stand-in for Inji Certify, for tests and for demoing the
presentation side when Certify / Collab eSignet is unavailable.

It produces credentials with the same shape as Chirayu's Certify setup:
  ldp_vc     FarmerCredential, Ed25519Signature2020, credentialSubject.id = holder did:jwk
  vc+sd-jwt  typ vc+sd-jwt, alg EdDSA, vct FarmerCredentialSdJwt, cnf.kid = holder did:jwk,
             farmerID selectively disclosable and nested (credentialSubject._sd)

The issuer is a did:key, so anything that resolves did:key can check it.
Credentials from here are marked "test issuer" everywhere they appear, so
nobody mistakes them for real Certify output.
"""
import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from jsonld_proofs import CREDENTIALS_V1, ED25519_2020_CONTEXT, b58encode, b64url, sign_ed25519_2020
from sdjwt import make_disclosure

FARMER_CONTEXT = "https://piyush7034.github.io/my-files/farmer.json"

# What Chirayu's Certify puts in its credentials as the issuer. Used only by the
# "forged issuer" negative test, which claims to be Certify without its key.
CERTIFY_ISSUER_DID = os.environ.get("CERTIFY_ISSUER_DID", "did:web:mushmat.github.io:inji_sandbox")
CERTIFY_SD_JWT_ISS = os.environ.get("CERTIFY_ISSUER_ID", "http://certify-nginx:80")

SAMPLE_SUBJECT = {
    "fullName": "Pandit Joshi",
    "mobileNumber": "9998882226",
    "dateOfBirth": "05-03-1987",
    "gender": "Female",
    "state": "Karnataka",
    "district": "Bangalore",
    "villageOrTown": "Koramangala",
    "postalCode": "560100",
    "landArea": "1 acres",
    "landOwnershipType": "Owner",
    "primaryCropType": "Maize",
    "secondaryCropType": "Rice",
    "farmerID": "987654321",
}


class TestIssuer:
    def __init__(self, private_key: ed25519.Ed25519PrivateKey = None):
        self.key = private_key or ed25519.Ed25519PrivateKey.generate()
        raw = self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.multibase = "z" + b58encode(b"\xed\x01" + raw)
        self.did = f"did:key:{self.multibase}"
        self.verification_method = f"{self.did}#{self.multibase}"

    def x5c(self) -> str:
        """Self-signed certificate for the issuer key, base64 DER (JWS x5c). Inji Verify
        0.18.2 takes an SD-JWT issuer's key only from x5c, as Certify sends it."""
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz
        if getattr(self, "_x5c", None):
            return self._x5c
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Playground test issuer (not trusted)")])
        now = _dt.now(_tz.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(self.key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - _td(days=1)).not_valid_after(now + _td(days=365))
                .sign(self.key, algorithm=None))
        import base64 as _b64
        self._x5c = _b64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode()
        return self._x5c

    def issue_ldp(self, holder_did: str, subject: dict = None, valid_days: int = 365, expired: bool = False,
                  forged: bool = False) -> dict:
        now = datetime.now(timezone.utc)
        exp = now - timedelta(days=1) if expired else now + timedelta(days=valid_days)
        vc = {
            "@context": [CREDENTIALS_V1, FARMER_CONTEXT, ED25519_2020_CONTEXT],
            "id": f"urn:uuid:{secrets.token_hex(16)}",
            "type": ["VerifiableCredential", "FarmerCredential"],
            "issuer": CERTIFY_ISSUER_DID if forged else self.did,
            "issuanceDate": (now - timedelta(days=2 if expired else 0)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "expirationDate": exp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "credentialSubject": {"id": holder_did, **(subject or SAMPLE_SUBJECT)},
        }
        return sign_ed25519_2020(vc, self.key, self.verification_method, "assertionMethod")

    def issue_sd_jwt(self, holder_did: str, subject: dict = None, sd_claims=("farmerID",), valid_days: int = 365,
                     expired: bool = False, forged: bool = False) -> str:
        subject = dict(subject or SAMPLE_SUBJECT)
        disclosures, digests = [], []
        for name in sd_claims:
            if name in subject:
                d = make_disclosure(name, subject.pop(name), b64url(os.urandom(16)))
                disclosures.append(d)
                digests.append(b64url(hashlib.sha256(d.encode("ascii")).digest()))
        now = int(time.time())
        payload = {
            "iss": CERTIFY_SD_JWT_ISS if forged else self.did,
            "iat": now - (2 * 86400 if expired else 0),
            "nbf": now - (2 * 86400 if expired else 0),
            "exp": now - 86400 if expired else now + valid_days * 86400,
            "vct": "FarmerCredentialSdJwt",
            "cnf": {"kid": holder_did},
            "credentialSubject": {**subject, "_sd": sorted(digests)},
            "_sd_alg": "sha-256",
        }
        headers = {"typ": "vc+sd-jwt", "x5c": [self.x5c()]}
        if not forged:
            headers["kid"] = self.verification_method
        token = pyjwt.encode(payload, self.key, algorithm="EdDSA", headers=headers)
        return token + "~" + "".join(d + "~" for d in disclosures)

    def issue(self, vc_format: str, holder_did: str, **kw):
        if vc_format == "ldp_vc":
            return self.issue_ldp(holder_did, **kw)
        if vc_format == "vc+sd-jwt":
            return self.issue_sd_jwt(holder_did, **kw)
        raise ValueError(f"the test issuer does not issue {vc_format}")

    def private_pem(self) -> bytes:
        return self.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())

    @classmethod
    def from_pem(cls, pem: bytes):
        return cls(serialization.load_pem_private_key(pem, None))


def pretty(obj) -> str:
    return json.dumps(obj, indent=2)
