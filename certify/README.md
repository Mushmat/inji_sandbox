# Certify (Issuer)

Owns the issuer side of the playground: standing up Inji Certify, configuring
credential formats, and proving the OpenID4VCI issuance flow works. Covers
FR1 (issuer side), FR3, and FR6 from the mandatory requirements, plus FR9
(third credential format) from the good-to-haves.

## Prerequisites

- Docker + Docker Compose
- Python 3.9+, with a virtualenv (`python3 -m venv .venv` in this directory,
  `source .venv/bin/activate`, then `pip install -r scripts/requirements.txt
  -r demo-ui/requirements.txt`) — Homebrew's Python won't let you `pip
  install` system-wide (PEP 668), so a venv is required, not optional
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
docker logs docker-compose-certify-1 -f
```

Wait for `===== INJI Certify -- Started =====` in the log, then verify:

```bash
curl -s http://localhost:8090/v1/certify/.well-known/did.json
curl -s http://localhost:8090/v1/certify/.well-known/openid-credential-issuer
```

Both should return `200` with real JSON, and the second one should list three
credential configurations: `FarmerCredential` (`ldp_vc`), `FarmerCredentialSdJwt`
(`vc+sd-jwt`), and `MobileDrivingLicense` (`mso_mdoc`) — all three are seeded
automatically from `docker-compose/certify_init.sql`, no manual setup needed.

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

## Credential formats (FR6 mandatory + FR9 good-to-have)

All three are the same underlying mock identity data
(`docker-compose/config/farmer_identity_data.csv`, via Certify's built-in
`MockCSVDataProviderPlugin`), issued in three different, clearly-labeled
formats:

| Config | Format | Scope | Notes |
|---|---|---|---|
| `FarmerCredential` | `ldp_vc` (W3C VC JSON-LD) | `mock_identity_vc_ldp` | Signed `Ed25519Signature2020`, RSA holder key |
| `FarmerCredentialSdJwt` | `vc+sd-jwt` (SD-JWT VC) | `mock_identity_vc_ldp` | `vct: FarmerCredentialSdJwt`, `farmerID` selectively disclosable, RSA holder key |
| `MobileDrivingLicense` | `mso_mdoc` (ISO 18013-5 mDL) | `mock_identity_vc_ldp` | CBOR + COSE_Sign1, **EC P-256 holder key** (COSE only supports EC device keys, not RSA — the one place this demo's holder key type actually varies by format) |

All three configs share the same OAuth scope on purpose — see
[`API_DOCUMENTATION.md`](API_DOCUMENTATION.md) for why (short version: the
scope is validated by the authorization server, not by Certify, and we don't
control what scopes are registered there — formats are disambiguated by the
`format`/`vct`/`doctype` field in the actual credential request instead,
which is by design, not a workaround).

`mso_mdoc` needed two real CSV columns (`givenName`, `familyName`) added
alongside the existing `fullName`, since mDL claims are split first/last
name, not one combined field — see `identity_store.py`'s `split_name` for how
those get derived automatically from whatever `fullName` is set to.

## Testing the issuance flow (FR3)

`scripts/test_issuance_flow.py` runs the complete OpenID4VCI pre-authorized/
auth-code flow end-to-end against MOSIP Collab's public mock eSignet as the
authorization server, and requests a real credential from the local Certify
instance above. No account or login needed — Collab's sandbox ships a public
pre-registered demo client for exactly this.

```bash
cd scripts
source ../.venv/bin/activate   # see Prerequisites
python3 test_issuance_flow.py ldp_vc        # JSON-LD Farmer Credential
python3 test_issuance_flow.py "vc+sd-jwt"   # SD-JWT Farmer Credential
python3 test_issuance_flow.py mso_mdoc      # mDoc/mDL Mobile Driving License
```

Exit code 0 and a `"credential": ...` payload in the output means it worked.
See [`API_DOCUMENTATION.md`](API_DOCUMENTATION.md) for example output and a
breakdown of what each flow step does.

For real assertions rather than eyeballing output, run:

```bash
python3 -m unittest test_credential_shape.py -v
```

14 checks across all three formats: each issues successfully, every step
returns 200, the JSON-LD proof type and issuer DID are correct, the SD-JWT
header/vct/holder binding are correct and `farmerID` is actually selectively
disclosable (absent from the plaintext payload, only reachable through its
disclosure), the mDoc doctype/signature/claims are correct and actually
substituted (not left as literal `${...}` template text), and a bad format or
an unreachable auth server both fail cleanly instead of throwing.

All of this — `issuance_flow.py`, the module both scripts and the demo UI
below share — treats network calls like they can fail, because they can:
every request has a timeout, and any network or unexpected-response error
comes back as a normal `{"ok": False, "error": ...}` result instead of an
uncaught exception.

## Demo UI

`demo-ui/` is a page for showing this working without reading terminal
output or touching a CSV file by hand — not the team's playground UI, just
the way to demo the issuer piece to teammates. It has:

- An identity editor — change the name/details credentials get issued for,
  right from the page. Saving restarts Certify (see below for why) and the
  UI shows that clearly rather than just hanging.
- All three credential formats as selectable cards.
- An expandable protocol timeline (click any step to see its raw response).
- A result view that adapts per format — a claims table for JSON-LD, decoded
  payload + disclosures for SD-JWT, decoded claims + signature status for
  mDoc — plus the raw credential behind a toggle for anyone who wants it.

The backend behind it is the same tested `issuance_flow.py`, wrapped in a
small Flask app with a `/healthz` endpoint, JSON error responses instead of
stack traces, and debug mode off by default. See
[`demo-ui/README.md`](demo-ui/README.md).

**Why saving identity data restarts Certify**: the bundled
`MockCSVDataProviderPlugin` loads `farmer_identity_data.csv` once at
container startup and doesn't re-read it per request — confirmed by testing
directly, editing the file alone didn't change what got issued, a restart
did. So `POST /api/identity` writes the file, then restarts the `certify`
container and waits for it to report healthy before responding. That's a
real ~1-2 minute wait, which is why the UI shows a "restarting" state instead
of just looking frozen.

## DID hosting

Certify's `did-url` is `did:web:mushmat.github.io:inji-did`, which resolves
to `https://mushmat.github.io/inji-did/did.json`.

This lives in its own small public repo (`inji-did`), separate from this one,
so the DID document can be public without needing the whole team repo to be
public yet. `docs/did.json` in *this* repo is kept as a reference copy of
what's published there — it is not itself served anywhere.

**To (re-)publish it:**
1. `curl http://localhost:8090/v1/certify/.well-known/did.json` — fetch the
   current document from the running instance
2. Put it at the root of the `inji-did` repo as `did.json`
3. Commit and push to `inji-did`
4. GitHub Pages on that repo (Settings → Pages → deploy from branch → `main`
   → `/` root) serves it automatically once pushed

The signing keys behind this are stored in Postgres and stay stable across
normal restarts — they only regenerate if the database volume gets wiped
(`docker-compose down -v`). If that happens, repeat the steps above to
re-publish the new document, or verifiers will fail signature checks against
a stale key.

## Architecture

This component is one piece of the larger playground — see the top-level
project README and architecture diagram for how Certify fits with the
Playground BFF, Wallet, and Verify pieces.
