"""Shared setup, imported first by every test module.

Everything the BFF and the certify/ and verify/ modules read from the environment is fixed here
before they're imported: a throwaway data folder, bundled JSON-LD contexts only, and a free port
for the in-process server the verifier tests talk to over real HTTP.
"""

import os
import socket
import sys
import tempfile
from pathlib import Path

BFF = Path(__file__).resolve().parents[1]
ROOT = BFF.parents[1]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT = _free_port()
BASE = f"http://127.0.0.1:{PORT}"
DATA = tempfile.mkdtemp(prefix="playground-tests-")

os.environ.update({
    "PLAYGROUND_DATA_DIR": DATA,
    "PLAYGROUND_PORT": str(PORT),
    "PLAYGROUND_PUBLIC_URL": BASE,
    "ALLOW_REMOTE_CONTEXTS": "0",
    # Certify's SD-JWT issuer id resolves to its DID document; the tests serve the published copy.
    "CERTIFY_DID_DOCUMENT_URL": f"{BASE}/__test__/certify-did.json",
    "WALLET_URL_REWRITES": "",
})
if str(BFF) not in sys.path:
    sys.path.insert(0, str(BFF))

import config  # noqa: E402,F401  (puts certify/scripts and verify/scripts on the path)
