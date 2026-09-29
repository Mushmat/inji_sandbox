"""Paths, service URLs and environment for the Playground BFF.

Imported first by everything else: the certify/ and verify/ modules read their
settings from the environment at import time, so it has to be ready before them.
"""

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CERTIFY_SCRIPTS = ROOT / "certify" / "scripts"
VERIFY_SCRIPTS = ROOT / "verify" / "scripts"
DATA_DIR = Path(os.environ.get("PLAYGROUND_DATA_DIR", ROOT / "playground" / ".data"))
WEB_DIST = Path(os.environ.get("PLAYGROUND_WEB_DIST", ROOT / "playground" / "web" / "dist"))


def _load_env_file(path: Path) -> None:
    # Written by integration/stack.py: the current tunnel address and how the
    # host-side wallet reaches Inji Verify. Real env vars still win.
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() and not line.lstrip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip())


_load_env_file(ROOT / "integration" / ".generated" / "verify.env")
DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("VERIFY_WALLET_DIR", str(DATA_DIR / "wallet"))
os.environ.setdefault("CERTIFY_SCRIPTS_DIR", str(CERTIFY_SCRIPTS))

for p in (CERTIFY_SCRIPTS, VERIFY_SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

PORT = int(os.environ.get("PLAYGROUND_PORT", "5050"))
HOST = os.environ.get("PLAYGROUND_HOST", "127.0.0.1")
# Where wallets reach the Playground verifier. stack.py sets an https tunnel address here so Inji Web can use it.
PLAYGROUND_PUBLIC_URL = os.environ.get("PLAYGROUND_PUBLIC_URL", f"http://localhost:{PORT}").rstrip("/")
CERTIFY_URL = os.environ.get("CERTIFY_URL", "http://localhost:8090/v1/certify")
CERTIFY_PREAUTH_URL = os.environ.get("CERTIFY_PREAUTH_URL", "http://localhost:8092/v1/certify")
CERTIFY_PUBLIC_ISSUER = "http://certify-nginx:80"
INJI_VERIFY_URL = os.environ.get("INJI_VERIFY_URL", "http://localhost:8080/v1/verify")
MIMOTO_URL = os.environ.get("MIMOTO_URL", "http://localhost:8099/v1/mimoto")
INJI_WEB_URL = os.environ.get("INJI_WEB_URL", "http://localhost:3004")
INJI_WEB_PROBE_URL = os.environ.get("INJI_WEB_PROBE_URL", INJI_WEB_URL)
PUBLISHED_DID_URL = os.environ.get("PUBLISHED_DID_URL", "https://mushmat.github.io/inji_sandbox/did.json")
DB_PATH = DATA_DIR / "runs.sqlite3"


def _image_versions() -> dict:
    """Module versions straight from the compose files, so the report never goes stale."""
    files = {
        "certify": ROOT / "certify" / "docker-compose" / "docker-compose.yaml",
        "wallet": ROOT / "wallet" / "docker-compose" / "docker-compose.yml",
        "verify": ROOT / "verify" / "docker-compose" / "docker-compose.yaml",
    }
    wanted = {
        "inji-certify": "Inji Certify",
        "mimoto": "Mimoto",
        "inji-web": "Inji Web",
        "inji-verify-service": "Inji Verify",
    }
    found = {}
    for path in files.values():
        if not path.exists():
            continue
        for image in re.findall(r"image:\s*['\"]?([\w./-]+):([\w.-]+)", path.read_text(encoding="utf-8")):
            name, tag = image
            for key, label in wanted.items():
                if name.split("/")[-1].startswith(key):
                    found[label] = tag
    return found


VERSIONS = _image_versions()
