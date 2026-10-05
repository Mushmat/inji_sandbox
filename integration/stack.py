"""Starts, stops and checks the whole playground: Certify (both instances), Inji Verify, the wallet,
the two https tunnels and the Playground itself.

Usage: python integration/stack.py up [--no-playground] | down | status
Works the same on macOS, Linux and Windows (PowerShell). Only needs Docker and Python.
--no-playground leaves the Playground out, for running playground/bff/main.py on the host while developing.
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
PLAYGROUND_COMPOSE = ROOT / "playground" / "docker-compose.yaml"
WALLET_DIR = ROOT / "wallet" / "docker-compose"
WALLET_COMPOSE = WALLET_DIR / "docker-compose.yml"
WALLET_PROJECT = "inji-wallet"

NETWORK = "mosip_network"
VERIFY_PORT = os.environ.get("VERIFY_PORT", "8080")
PUBLISHED_DID = "https://mushmat.github.io/inji_sandbox/did.json"

# (container, what it exposes over https)
TUNNELS = {
    "verify": ("inji-verify-tunnel", "http://verify-service:8080"),
    # host.docker.internal works whether the Playground runs in its container (port 5050 is published)
    # or straight on the host.
    "playground": ("inji-playground-tunnel", "http://host.docker.internal:5050"),
}
# Wallet-side client_id for each verifier (verify/scripts/verifier_client.py, playground/bff/verifier_service.py)
VERIFIERS = {
    "verify": ("inji-sandbox-playground", "/v1/verify/vp-submission/direct-post"),
    "playground": ("playground-verifier", "/verifier/v1/verify/vp-submission/direct-post"),
}

CHECKS = [
    ("Certify (eSignet login)", "http://localhost:8090/v1/certify/.well-known/openid-credential-issuer", {200}),
    ("Certify (pre-authorized)", "http://localhost:8092/v1/certify/.well-known/openid-credential-issuer", {200}),
    ("Inji Verify", f"http://localhost:{VERIFY_PORT}/v1/verify/vp-request/x/status", {404}),
    ("Mimoto", "http://localhost:8099/v1/mimoto/issuers", {200}),
    ("Inji Web", "http://localhost:3004", {200}),
    ("Playground", "http://localhost:5050/api/catalog", {200}),
]


def docker_env() -> dict:
    env = dict(os.environ)
    # The MOSIP images are amd64 only; Apple Silicon runs them under emulation.
    if platform.machine().lower() in ("arm64", "aarch64"):
        env.setdefault("DOCKER_DEFAULT_PLATFORM", "linux/amd64")
    return env


def run(args, env=None, check=True, capture=False):
    return subprocess.run(args, env=env or docker_env(), check=check, text=True, capture_output=capture)


def compose(*args, env=None):
    run(["docker", "compose", *args], env=env)


def certify_files() -> list:
    """Compose skips docker-compose.override.yaml once -f is given, and that override is what loads
    the shared signing key (certify/README.md), so pass it explicitly when it's there."""
    files = ["-f", str(CERTIFY_COMPOSE)]
    for name in ("docker-compose.override.yaml", "docker-compose.override.yml"):
        if (CERTIFY_COMPOSE.parent / name).exists():
            files += ["-f", str(CERTIFY_COMPOSE.parent / name)]
    return files


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
        # Built inside the Playground image, which has the crypto libraries, so the host only
        # needs plain Python to run this script.
        print("Wallet keystore missing, generating it...")
        env = dict(os.environ)  # the Playground image is multi-arch, no emulation needed
        compose("-f", str(PLAYGROUND_COMPOSE), "build", env=env)
        run(["docker", "run", "--rm", "-v", f"{ROOT}:/app", "-w", "/app", "inji-playground:local",
             "python", "integration/make_wallet_keystore.py"], env=env)


def start_tunnel(name: str, target: str) -> str:
    state = run(["docker", "inspect", "-f", "{{.State.Running}}", name], check=False, capture=True)
    if state.stdout.strip() != "true":
        run(["docker", "rm", "-f", name], check=False, capture=True)
        # http2 instead of the default QUIC: many college and office networks drop
        # the UDP it needs, and the tunnel then silently answers 530.
        run(["docker", "run", "-d", "--name", name, "--network", NETWORK, "--restart", "unless-stopped",
             "--add-host", "host.docker.internal:host-gateway",
             "cloudflare/cloudflared:latest", "tunnel", "--no-autoupdate", "--protocol", "http2",
             "--url", target], capture=True)
    for _ in range(60):
        logs = run(["docker", "logs", name], check=False, capture=True)
        found = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", logs.stdout + logs.stderr)
        if found:
            return found[-1]
        time.sleep(1)
    sys.exit(f"The tunnel {name} didn't report an address within a minute. Check `docker logs {name}`.")


def write_wallet_override(tunnels: dict) -> bool:
    """Adds both verifiers to the wallet's trusted list. Returns True if the list changed."""
    GENERATED.mkdir(parents=True, exist_ok=True)
    verifiers = json.loads((WALLET_DIR / "config" / "mimoto-trusted-verifiers.json").read_text(encoding="utf-8-sig"))
    ours = {client_id for client_id, _ in VERIFIERS.values()}
    verifiers["verifiers"] = [v for v in verifiers["verifiers"] if v.get("client_id") not in ours]
    for key, (client_id, path) in VERIFIERS.items():
        verifiers["verifiers"].append({
            "client_id": client_id,
            "redirect_uris": [],
            "response_uris": [tunnels[key] + path],
            # Both verifiers send unsigned requests; Mimoto refuses those otherwise (FINDINGS W6).
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


def up(with_playground=True):
    check_local_files()
    ensure_network()

    print("\n== Certify (eSignet login + pre-authorized) ==")
    compose(*certify_files(), "up", "-d")

    print("\n== https tunnels ==")
    tunnels = {key: start_tunnel(name, target) for key, (name, target) in TUNNELS.items()}
    for key, url in tunnels.items():
        print(f"{key:<11} {url}")

    print("\n== Inji Verify ==")
    env = docker_env()
    env.update(VERIFY_PORT=VERIFY_PORT, VERIFY_PUBLIC_URL=tunnels["verify"])
    compose("-f", str(VERIFY_COMPOSE), "up", "-d", env=env)

    print("\n== Wallet (Mimoto + Inji Web) ==")
    changed = write_wallet_override(tunnels)
    wallet_compose("up", "-d")
    if changed:
        # Mimoto caches the trusted verifier list, so new tunnel addresses need a restart.
        run(["docker", "restart", "mimoto-service"], capture=True)

    # For the Playground (or verify/demo-ui) running on the host rather than in its container.
    (GENERATED / "verify.env").write_text(
        f"INJI_VERIFY_URL=http://localhost:{VERIFY_PORT}/v1/verify\n"
        f"PLAYGROUND_PUBLIC_URL={tunnels['playground']}\n"
        f"WALLET_URL_REWRITES={tunnels['verify']}=http://localhost:{VERIFY_PORT},"
        f"{tunnels['playground']}=http://localhost:5050\n", encoding="utf-8")

    if with_playground:
        print("\n== Playground ==")
        env = dict(os.environ)  # the Playground image is multi-arch, no emulation needed
        env.update(PLAYGROUND_PUBLIC_URL=tunnels["playground"],
                   WALLET_URL_REWRITES=f"{tunnels['verify']}=http://verify-service:8080,"
                                       f"{tunnels['playground']}=http://127.0.0.1:5050")
        compose("-f", str(PLAYGROUND_COMPOSE), "up", "-d", "--build", env=env)

    print("\nStarted. The Java services take a few minutes to boot (longer on Apple Silicon).")
    print("Run `python integration/stack.py status` until everything shows up, then open http://localhost:5050")


def down():
    compose("-f", str(PLAYGROUND_COMPOSE), "down")
    wallet_override = GENERATED / "wallet.override.yml"
    if wallet_override.exists():
        wallet_compose("down")
    else:
        compose("-p", WALLET_PROJECT, "-f", str(WALLET_COMPOSE), "down")
    compose("-f", str(VERIFY_COMPOSE), "down")
    for name, _ in TUNNELS.values():
        run(["docker", "rm", "-f", name], check=False, capture=True)
    compose(*certify_files(), "down")
    print("Stopped. Databases and keys are kept; nothing was deleted.")


def status():
    width = max(len(n) for n, _, _ in CHECKS)
    for name, url, ok in CHECKS:
        up_ = http_status(url) in ok
        print(f"  {name:<{width}}  {'up' if up_ else 'not ready':<9}  {url}")

    generated = GENERATED / "verify.env"
    if generated.exists():
        print("\n  " + generated.read_text(encoding="utf-8").strip().replace("\n", "\n  "))

    live = did_keys("http://localhost:8090/v1/certify/.well-known/did.json")
    if live:
        if live == did_keys(PUBLISHED_DID):
            print("\n  Certify's keys match the published DID document.")
        else:
            print("\n  WARNING: Certify's keys don't match the published DID document, so wallets and verifiers")
            print("  will reject its credentials. See certify/README.md, 'Running this issuer on another machine'.")
    print("\n  Playground: http://localhost:5050   Inji Web: http://localhost:3004")


def main():
    args = sys.argv[1:]
    if args[:1] == ["up"] and set(args[1:]) <= {"--no-playground"}:
        up(with_playground="--no-playground" not in args)
    elif args in (["down"], ["status"]):
        {"down": down, "status": status}[args[0]]()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
