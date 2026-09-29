#!/usr/bin/env python3
"""
Share one set of Inji Certify signing keys across the team's machines.

Why: the issuer DID (did:web:mushmat.github.io:inji-did) points at ONE hosted
did.json, so every Certify that issues under that DID must sign with the same
keys. Certify 0.14.0 makes new keys on every fresh database, so without this
each teammate's Certify signs with keys the hosted did.json doesn't have, and
Inji Verify rejects its credentials (verify/docs/FINDINGS.md, D1).

Where Certify keeps its keys (checked on a running 0.14.0 container):
  - master keys: PKCS12 keystore /home/inji/CERTIFY_PKCS12/local.p12 inside
    the certify container (NOT the /home/mosip/CERTIFY_PKCS12 folder that
    certify/docker-compose mounts, so it is lost when the container is recreated)
  - the Ed25519 signing key: encrypted in certify.key_store, with the key
    metadata in certify.key_alias (and certificates in certify.ca_cert_store)

Usage (run from anywhere; needs Docker and Chirayu's certify/docker-compose running):

    # on the machine whose keys are in the hosted did.json (Chirayu's):
    python3 certify_keys.py export              -> certify-keys-YYYYMMDD-HHMM.zip

    # on every other machine, with its Certify stack up:
    python3 certify_keys.py import certify-keys-....zip

    python3 certify_keys.py check               # do local and hosted did.json keys match?

The zip holds private key material: share it only inside the team, never commit it.
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_COMPOSE_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "certify", "docker-compose"))
P12_IN_CONTAINER = "/home/inji/CERTIFY_PKCS12/local.p12"
TABLES = ["certify.key_alias", "certify.key_store", "certify.ca_cert_store"]
DB_NAME, DB_USER = "inji_certify", "postgres"
LOCAL_DID_URL = os.environ.get("CERTIFY_DID_DOCUMENT_URL", "http://localhost:8090/v1/certify/.well-known/did.json")


def run(args, input_bytes=None, check=True):
    p = subprocess.run(args, input=input_bytes, capture_output=True)
    if check and p.returncode != 0:
        raise SystemExit(f"command failed: {' '.join(args)}\n{p.stderr.decode(errors='replace')[:2000]}")
    return p


def container(compose_dir, service):
    out = run(["docker", "compose", "--project-directory", compose_dir, "ps", "-a", "-q", service]).stdout.decode().strip()
    if not out:
        raise SystemExit(f"no '{service}' container for {compose_dir}. Start it first: "
                         f"cd {compose_dir} && docker compose up -d")
    return out.splitlines()[0]


def fetch_json(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def did_keys(doc):
    return {vm["id"]: vm.get("publicKeyMultibase") or json.dumps(vm.get("publicKeyJwk"), sort_keys=True)
            for vm in doc.get("verificationMethod", [])}


def hosted_url(did):
    parts = did[len("did:web:"):].split(":")
    return f"https://{parts[0]}/{'/'.join(parts[1:])}/did.json" if len(parts) > 1 else f"https://{parts[0]}/.well-known/did.json"


def wait_for_certify(timeout=300):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            return fetch_json(LOCAL_DID_URL, timeout=5)
        except Exception:
            time.sleep(5)
    raise SystemExit(f"Certify did not come back within {timeout}s ({LOCAL_DID_URL})")


# ------------------------------------------------------------------ export
def export(compose_dir, out_path):
    certify, db = container(compose_dir, "certify"), container(compose_dir, "database")
    tmp = tempfile.mkdtemp()
    try:
        p12 = os.path.join(tmp, "local.p12")
        run(["docker", "cp", f"{certify}:{P12_IN_CONTAINER}", p12])
        dump = run(["docker", "exec", db, "pg_dump", "-U", DB_USER, "-d", DB_NAME, "--data-only"]
                   + sum((["-t", t] for t in TABLES), [])).stdout
        did_doc = fetch_json(LOCAL_DID_URL)
        manifest = {"made_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "did": did_doc.get("id"),
                    "keys": did_keys(did_doc), "tables": TABLES, "p12_path_in_container": P12_IN_CONTAINER,
                    "certify_image": "injistack/inji-certify-with-plugins:0.14.0"}
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(p12, "local.p12")
            z.writestr("keys.sql", dump)
            z.writestr("did.json", json.dumps(did_doc, indent=2))
            z.writestr("manifest.json", json.dumps(manifest, indent=2))
            z.writestr("README.txt", "Inji Certify signing keys. PRIVATE: share only inside the team, never commit.\n"
                                     "Import with: python3 certify_keys.py import <this zip>\n")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"exported keys of {manifest['did']} to {out_path}")
    for vm, k in manifest["keys"].items():
        print(f"  {vm.split('#')[-1][:16]}...  {k[:24]}...")
    _compare_hosted(did_doc)


# ------------------------------------------------------------------ import
def import_(compose_dir, bundle):
    with zipfile.ZipFile(bundle) as z:
        p12_bytes, sql = z.read("local.p12"), z.read("keys.sql")
        manifest = json.loads(z.read("manifest.json"))
    certify, db = container(compose_dir, "certify"), container(compose_dir, "database")
    print(f"importing keys of {manifest['did']} (exported {manifest['made_at']})")

    print("  stopping certify ...")
    run(["docker", "stop", certify])
    print("  replacing key tables ...")
    script = ("BEGIN;\nTRUNCATE " + ", ".join(TABLES) + ";\n").encode() + sql + b"\nCOMMIT;\n"
    run(["docker", "exec", "-i", db, "psql", "-U", DB_USER, "-d", DB_NAME, "-v", "ON_ERROR_STOP=1", "-q"], input_bytes=script)
    print("  replacing keystore ...")
    tmp = tempfile.mkdtemp()
    try:
        p12 = os.path.join(tmp, "local.p12")
        with open(p12, "wb") as f:
            f.write(p12_bytes)
        run(["docker", "cp", p12, f"{certify}:{P12_IN_CONTAINER}"])
        # also keep a copy where a fixed compose mount would read it (see verify/patches/README.md)
        host_dir = os.path.join(compose_dir, "data", "CERTIFY_PKCS12")
        os.makedirs(host_dir, exist_ok=True)
        shutil.copyfile(p12, os.path.join(host_dir, "local.p12"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("  starting certify (1-3 minutes) ...")
    run(["docker", "start", certify])
    doc = wait_for_certify()
    now = did_keys(doc)
    if now != manifest["keys"]:
        raise SystemExit("Certify is up but its keys are NOT the imported ones:\n"
                         f"  expected {manifest['keys']}\n  got      {now}")
    print("  done: this Certify now signs with the imported keys")
    _compare_hosted(doc)


# ------------------------------------------------------------------- check
def _compare_hosted(local_doc):
    did = local_doc.get("id", "")
    if not did.startswith("did:web:"):
        return True
    url = hosted_url(did)
    try:
        hosted = fetch_json(url)
    except Exception as e:
        print(f"  hosted DID document not reachable ({url}): {e}")
        return False
    same = did_keys(hosted) == did_keys(local_doc)
    print(f"  hosted {url}: {'MATCHES' if same else 'DOES NOT MATCH'} this Certify's keys")
    if not same:
        print("  -> either import the keys whose did.json is hosted, or publish this Certify's did.json there")
    return same


def check():
    return _compare_hosted(fetch_json(LOCAL_DID_URL))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["export", "import", "check"])
    ap.add_argument("bundle", nargs="?", help="zip to write (export) or read (import)")
    ap.add_argument("--compose-dir", default=DEFAULT_COMPOSE_DIR, help="certify/docker-compose folder")
    a = ap.parse_args()
    if a.action == "export":
        export(a.compose_dir, a.bundle or f"certify-keys-{time.strftime('%Y%m%d-%H%M')}.zip")
    elif a.action == "import":
        if not a.bundle:
            ap.error("import needs the zip file")
        import_(a.compose_dir, a.bundle)
    else:
        sys.exit(0 if check() else 1)


if __name__ == "__main__":
    main()
