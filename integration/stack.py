"""Starts, stops and checks the whole local stack: Certify, Inji Verify, the https tunnel and the wallet.

Usage: python integration/stack.py up | down | status
Works the same on macOS, Linux and Windows (PowerShell). Only needs Docker and Python.
"""

import json
import os
import platform
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "integration" / ".generated"

CERTIFY_COMPOSE = ROOT / "certify" / "docker-compose" / "docker-compose.yaml"
VERIFY_COMPOSE = ROOT / "verify" / "docker-compose" / "docker-compose.yaml"
WALLET_DIR = ROOT / "wallet" / "docker-compose"
WALLET_COMPOSE = WALLET_DIR / "docker-compose.yml"
WALLET_PROJECT = "inji-wallet"

NETWORK = "mosip_network"
TUNNEL = "inji-verify-tunnel"
VERIFY_PORT = os.environ.get("VERIFY_PORT", "8080")
VERIFY_CLIENT_ID = os.environ.get("VERIFY_CLIENT_ID", "inji-sandbox-playground")
PUBLISHED_DID = "https://mushmat.github.io/inji_sandbox/did.json"

CHECKS = [
    ("Certify", "http://localhost:8090/v1/certify/.well-known/openid-credential-issuer", {200}),
    ("Inji Verify", f"http://localhost:{VERIFY_PORT}/v1/verify/vp-request/x/status", {404}),
    ("Mimoto", "http://localhost:8099/v1/mimoto/issuers", {200}),
    ("Inji Web", "http://localhost:3004", {200}),
]


def docker_env() -> dict:
    env = dict(os.environ)
    # The MOSIP images are amd64 only; Apple Silicon runs them under emulation.
    if platform.machine().lower() in ("arm64", "aarch64"):
        env.setdefault("DOCKER_DEFAULT_PLATFORM", "linux/amd64")
    return env


def run(args, env=None, check=True, capture=False):
    return subprocess.run(args, env=env or docker_env(), check=check, text=True,
                          capture_output=capture)


def compose(*args, env=None):
    run(["docker", "compose", *args], env=env)


def http_status(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, OSError):
        return 0


def ensure_network():
    if run(["docker", "network", "inspect", NETWORK], check=False, capture=True).returncode != 0:
        run(["docker", "network", "create", NETWORK])


def check_local_files():
    if not (WALLET_DIR / ".env").exists():
        sys.exit("wallet/docker-compose/.env is missing. Create your Google OAuth client first, see wallet/README.md step 3.")
    if not (WALLET_DIR / "certs" / "oidckeystore.p12").exists():
        print("Wallet keystore missing, generating it...")
        run([sys.executable, str(ROOT / "integration" / "make_wallet_keystore.py")])


def start_tunnel() -> str:
    state = run(["docker", "inspect", "-f", "{{.State.Running}}", TUNNEL], check=False, capture=True)
    if state.stdout.strip() != "true":
        run(["docker", "rm", "-f", TUNNEL], check=False, capture=True)
        # http2 instead of the default QUIC: many college and office networks drop
        # the UDP it needs, and the tunnel then silently answers 530.
        run(["docker", "run", "-d", "--name", TUNNEL, "--network", NETWORK, "--restart", "unless-stopped",
             "cloudflare/cloudflared:latest", "tunnel", "--no-autoupdate", "--protocol", "http2",
             "--url", "http://verify-service:8080"], capture=True)
    for _ in range(60):
        logs = run(["docker", "logs", TUNNEL], check=False, capture=True)
        found = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", logs.stdout + logs.stderr)
        if found:
            return found[-1]
        time.sleep(1)
    sys.exit("The tunnel didn't report an address within a minute. Check `docker logs inji-verify-tunnel`.")


def write_wallet_override(tunnel_url: str) -> bool:
    """Adds our verifier to the wallet's trusted list. Returns True if the list changed."""
    GENERATED.mkdir(parents=True, exist_ok=True)
    verifiers = json.loads((WALLET_DIR / "config" / "mimoto-trusted-verifiers.json").read_text(encoding="utf-8-sig"))
    verifiers["verifiers"] = [v for v in verifiers["verifiers"] if v.get("client_id") != VERIFY_CLIENT_ID]
    verifiers["verifiers"].append({
        "client_id": VERIFY_CLIENT_ID,
        "redirect_uris": [],
        "response_uris": [f"{tunnel_url}/v1/verify/vp-submission/direct-post"],
        # Inji Verify sends unsigned requests; Mimoto refuses those otherwise (FINDINGS W6).
        "allow_unsigned_request": True,
    })
    verifiers_file = GENERATED / "mimoto-trusted-verifiers.json"
    new = json.dumps(verifiers, indent=2)
    changed = not verifiers_file.exists() or verifiers_file.read_text(encoding="utf-8") != new
    verifiers_file.write_text(new, encoding="utf-8")
    (GENERATED / "wallet.override.yml").write_text(
        "services:\n"
        "  inji-web:\n"
        "    volumes:\n"
        f"      - {verifiers_file.as_posix()}:/home/mosip/mimoto-trusted-verifiers.json\n",
        encoding="utf-8")
    return changed


def wallet_compose(*args):
    compose("-p", WALLET_PROJECT, "--project-directory", str(WALLET_DIR),
            "-f", str(WALLET_COMPOSE), "-f", str(GENERATED / "wallet.override.yml"), *args)


def did_keys(url: str) -> set:
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            doc = json.load(r)
        return {vm.get("publicKeyMultibase") for vm in doc.get("verificationMethod", [])}
    except (urllib.error.URLError, OSError, ValueError):
        return set()


def up():
    check_local_files()
    ensure_network()

    print("\n== Certify ==")
    compose("-f", str(CERTIFY_COMPOSE), "up", "-d")

    print("\n== https tunnel for Inji Verify ==")
    tunnel_url = start_tunnel()
    print(tunnel_url)

    print("\n== Inji Verify ==")
    env = docker_env()
    env.update(VERIFY_PORT=VERIFY_PORT, VERIFY_PUBLIC_URL=tunnel_url)
    compose("-f", str(VERIFY_COMPOSE), "up", "-d", env=env)

    print("\n== Wallet (Mimoto + Inji Web) ==")
    changed = write_wallet_override(tunnel_url)
    wallet_compose("up", "-d")
    if changed:
        # Mimoto caches the trusted verifier list, so a new tunnel address needs a restart.
        run(["docker", "restart", "mimoto-service"], capture=True)

    (GENERATED / "verify.env").write_text(
        f"INJI_VERIFY_URL=http://localhost:{VERIFY_PORT}/v1/verify\n"
        f"WALLET_URL_REWRITES={tunnel_url}=http://localhost:{VERIFY_PORT}\n", encoding="utf-8")

    print("\nStarted. The Java services take a few minutes to boot (longer on Apple Silicon).")
    print("Run `python integration/stack.py status` until everything shows up.")


def down():
    wallet_override = GENERATED / "wallet.override.yml"
    if wallet_override.exists():
        wallet_compose("down")
    else:
        compose("-p", WALLET_PROJECT, "-f", str(WALLET_COMPOSE), "down")
    compose("-f", str(VERIFY_COMPOSE), "down")
    run(["docker", "rm", "-f", TUNNEL], check=False, capture=True)
    compose("-f", str(CERTIFY_COMPOSE), "down")
    print("Stopped. Databases and keys are kept; nothing was deleted.")


def status():
    width = max(len(n) for n, _, _ in CHECKS)
    all_up = True
    for name, url, ok in CHECKS:
        code = http_status(url)
        up_ = code in ok
        all_up &= up_
        print(f"  {name:<{width}}  {'up' if up_ else 'not ready':<9}  {url}")

    tunnel = GENERATED / "verify.env"
    if tunnel.exists():
        print("\n  " + tunnel.read_text(encoding="utf-8").strip().replace("\n", "\n  "))

    live = did_keys("http://localhost:8090/v1/certify/.well-known/did.json")
    if live:
        published = did_keys(PUBLISHED_DID)
        if live == published:
            print("\n  Certify's keys match the published DID document.")
        else:
            print("\n  WARNING: Certify's keys don't match the published DID document, so wallets and verifiers")
            print("  will reject its credentials. See certify/README.md, 'Running this issuer on another machine'.")
    if all_up:
        print("\n  Inji Web: http://localhost:3004")


def main():
    commands = {"up": up, "down": down, "status": status}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit(__doc__)
    commands[sys.argv[1]]()


if __name__ == "__main__":
    main()
