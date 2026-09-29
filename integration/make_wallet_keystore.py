"""Wraps MOSIP's public wallet-demo client key into the oidckeystore.p12 Mimoto needs.

Usage: python integration/make_wallet_keystore.py [--force]
"""

import datetime
import json
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import BestAvailableEncryption, pkcs12
from cryptography.x509.oid import NameOID
from jwt.algorithms import RSAAlgorithm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "certify" / "scripts"))
from issuance_flow import PRIVATE_KEY_JWK  # noqa: E402

# Must match client_alias in mimoto-issuers-config.json and oidc_p12_password
# in wallet/docker-compose/docker-compose.yml.
ALIAS = b"wallet-demo-client"
PASSWORD = b"dummypassword"
OUT = ROOT / "wallet" / "docker-compose" / "certs" / "oidckeystore.p12"


def build() -> bytes:
    key = RSAAlgorithm.from_jwk(json.dumps(PRIVATE_KEY_JWK))
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "wallet-demo-client")])
    now = datetime.datetime.now(datetime.timezone.utc)
    # Java keystores want a certificate next to every private key entry.
    # Nothing checks this one, it's self-signed and long-lived on purpose.
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .sign(key, hashes.SHA256())
    )
    return pkcs12.serialize_key_and_certificates(ALIAS, key, cert, None, BestAvailableEncryption(PASSWORD))


def main() -> int:
    force = "--force" in sys.argv
    if OUT.exists() and not force:
        print(f"{OUT} already exists, leaving it alone (--force to rebuild).")
        print("If Mimoto has already run with the old one, rebuild and then wipe its volume, see wallet/README.md.")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(build())
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
