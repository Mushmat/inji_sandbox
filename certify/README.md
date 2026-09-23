# Certify (Issuer)

Owns the issuer side of the playground: standing up Inji Certify, configuring
credential formats, and proving the OpenID4VCI issuance flow works. Covers
FR1 (issuer side), FR3, and FR6 from the project requirements.

## Prerequisites

- Docker + Docker Compose
- Python 3.9+ (for the test script)
- On Apple Silicon: `export DOCKER_DEFAULT_PLATFORM=linux/amd64` before
  running Docker Compose — the upstream Certify images aren't published for
  arm64 yet, so this runs them under emulation. Slightly slower to boot,
  not a sign anything is broken.

## Run it

```bash
cd docker-compose
docker network create mosip_network   # only needed the first time on a machine
export DOCKER_DEFAULT_PLATFORM=linux/amd64
docker-compose up -d
```

First boot takes 3-6 minutes (key generation, DB migrations, Rosetta
emulation on Apple Silicon). Watch it with:

```bash
docker logs docker-compose-injistack-certify-1 -f
```

Wait for `===== INJI Certify -- Started =====` in the log, then verify:

```bash
curl -s http://localhost:8090/v1/certify/.well-known/did.json
curl -s http://localhost:8090/v1/certify/.well-known/openid-credential-issuer
```

Both should return `200` with real JSON, and the second one should list two
credential configurations: `FarmerCredential` (`ldp_vc`) and
`FarmerCredentialSdJwt` (`vc+sd-jwt`) — both are seeded automatically from
`docker-compose/certify_init.sql`, no manual setup needed.

Stop with `docker-compose down` (keeps data) or `docker-compose down -v`
(wipes and re-seeds clean next time).

All three services have real health checks (Postgres via `pg_isready`,
Certify and its Nginx via the well-known endpoint), and `depends_on` is
wired to wait for those, not just for the container to start. So
`docker-compose up -d` will sit there until Certify is actually ready
rather than returning immediately — that's expected, not a hang.

## What's running

Certify + its Nginx + Postgres only — this repo's Wallet and Verify pieces
run and are documented separately; see their own top-level folders.

| Service | Port |
|---|---|
| Certify API | 8090 |
| Certify Nginx | 8091 |
| Postgres | 5433 |

## Credential formats (FR6)

Both are the same underlying "Farmer Credential" mock identity data
(`docker-compose/config/farmer_identity_data.csv`, via Certify's built-in
`MockCSVDataProviderPlugin`), issued in two different, clearly-labeled
formats:

| Config | Format | Scope | Notes |
|---|---|---|---|
| `FarmerCredential` | `ldp_vc` (W3C VC JSON-LD) | `mock_identity_vc_ldp` | Signed `Ed25519Signature2020` |
| `FarmerCredentialSdJwt` | `vc+sd-jwt` (SD-JWT VC) | `mock_identity_vc_ldp` | `vct: FarmerCredentialSdJwt`, `farmerID` is selectively disclosable |

Both configs share the same OAuth scope on purpose — see
[`API_DOCUMENTATION.md`](API_DOCUMENTATION.md) for why (short version: the
scope is validated by the authorization server, not by Certify, and we don't
control what scopes are registered there — the two formats are disambiguated
by the `format`/`vct` field in the actual credential request instead, which
is by design, not a workaround).

## Testing the issuance flow (FR3)

`scripts/test_issuance_flow.py` runs the complete OpenID4VCI pre-authorized/
auth-code flow end-to-end against MOSIP Collab's public mock eSignet as the
authorization server, and requests a real credential from the local Certify
instance above. No account or login needed — Collab's sandbox ships a public
pre-registered demo client for exactly this.

```bash
cd scripts
pip install -r requirements.txt
python3 test_issuance_flow.py ldp_vc        # JSON-LD Farmer Credential
python3 test_issuance_flow.py "vc+sd-jwt"   # SD-JWT Farmer Credential
```

Exit code 0 and a `"credential": ...` payload in the output means it worked.
See [`API_DOCUMENTATION.md`](API_DOCUMENTATION.md) for example output and a
breakdown of what each flow step does.

For real assertions rather than eyeballing output, run:

```bash
python3 -m unittest test_credential_shape.py -v
```

11 checks: both formats issue successfully, every step returns 200, the
JSON-LD proof type and issuer DID are correct, the SD-JWT header/vct/holder
binding are correct, `farmerID` is actually selectively disclosable (absent
from the plaintext payload, only reachable through its disclosure), and a
bad format or an unreachable auth server both fail cleanly instead of
throwing.

All of this — `issuance_flow.py`, the module both scripts and the demo UI
below share — treats network calls like they can fail, because they can:
every request has a timeout, and any network or unexpected-response error
comes back as a normal `{"ok": False, "error": ...}` result instead of an
uncaught exception.

## Demo UI

`demo-ui/` is a small toy page for showing this working without reading
terminal output — two buttons, one per format, shows the protocol steps and
the resulting credential. Not the team's playground UI, just a quick way to
demo the issuer piece. The page itself is intentionally simple; the backend
behind it is the same tested `issuance_flow.py`, wrapped in a small Flask
app with a `/healthz` endpoint, JSON error responses instead of stack traces,
and debug mode off by default. See [`demo-ui/README.md`](demo-ui/README.md).

## DID hosting

Certify's `did-url` is set to `did:web:mushmat.github.io:inji_sandbox`, which
resolves to `https://mushmat.github.io/inji_sandbox/did.json`. That file is
sitting ready at `/docs/did.json` at the repo root — it just needs GitHub
Pages turned on to actually go live:

1. GitHub → repo → Settings → Pages
2. Source: deploy from a branch
3. Branch: `main` (or `feature/certify-issuer` if you want it live before the
   merge), folder `/docs`
4. Save — GitHub gives you the live URL, should match the one above

The signing key behind this is stored in Postgres and stays stable across
normal restarts — it only regenerates if the database volume gets wiped
(`docker-compose down -v`). If that ever happens, re-fetch and replace
`docs/did.json` with `curl http://localhost:8090/v1/certify/.well-known/did.json`.

## Architecture

This component is one piece of the larger playground — see the top-level
project README and architecture diagram for how Certify fits with the
Playground BFF, Wallet, and Verify pieces.
