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
docker logs inji-certify-certify-1 -f
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

Two Certify instances, their Nginx and one Postgres. The Wallet and Verify pieces
run and are documented separately; see their own top-level folders.

| Service | Port | What it is |
|---|---|---|
| `certify` | 8090 | Holders log in through MOSIP Collab's mock eSignet (authorization code). Reads the person from `farmer_identity_data.csv`. Inji Web uses this one |
| `certify-preauth` | 8092 | Pre-authorized code: Certify writes the credential offer and is its own authorization server. The person's details come with each offer |
| `certify-nginx` | 8091 | Serves `/.well-known` for `certify` |
| `database` | 5433 | Shared by both, so they have the same signing keys and the same `did:web` |

### Why two

A Certify instance trusts exactly one token issuer (`mosip.certify.authn.issuer-uri`,
see `AccessTokenValidationFilter`) and runs exactly one data provider plugin. The
pre-authorized flow needs Certify's own tokens and `PreAuthDataProviderPlugin`; Inji
Web needs eSignet's tokens and the CSV plugin. So the second instance runs the same
image and database with `config/certify-preauth.properties` on top. Its offers look
like this:

```
POST /v1/certify/pre-authorized-data  {"credential_configuration_id": "FarmerCredentialSdJwt", "claims": {...}}
  -> {"credential_offer_uri": "openid-credential-offer://?credential_offer_uri=http://certify-preauth:8090/v1/certify/credential-offer-data/<id>"}
```

`scripts/issuance_flow.py` has both flows: `run_issuance()` (eSignet login) and
`run_preauth_issuance()` (offer, pre-authorized code, token, credential).

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

Certify's `did-url` is `did:web:mushmat.github.io:inji_sandbox`, which
resolves to `https://mushmat.github.io/inji_sandbox/did.json`. That's served
by GitHub Pages from `docs/did.json` in this repo (Settings → Pages → deploy
from branch → `feature/certify-issuer` → `/docs`).

**To re-publish it:**
1. `curl -s http://localhost:8090/v1/certify/.well-known/did.json | python3 -m json.tool --indent 4 > ../docs/did.json`
   (from `certify/`)
2. Commit and push — Pages picks it up in a minute or two

The signing keys live in two places: `data/CERTIFY_PKCS12/local.p12` (the
actual keystore) and the `key_alias`/`key_store` tables in Postgres. Both
survive restarts. `docker-compose down -v` wipes the Postgres half, which
makes Certify generate new keys — if that happens, re-publish, or verifiers
will fail signature checks against the old key.

### Running this issuer on another machine

A second Certify instance generates its own keys, which won't match the
published DID. To make it sign with the same keys, it needs a copy of
`local.p12` and the matching `key_alias`/`key_store` rows. These are real
private keys, so they're shared directly between teammates, never committed
(`*.p12` and `*.local.sql` are gitignored).

1. Put the keystore at `docker-compose/data/CERTIFY_PKCS12/local.p12`
2. Put the SQL at `docker-compose/keys_seed.local.sql`. Its first line must be
   `\c inji_certify postgres`: Postgres runs each init script on a fresh connection to
   the default database, and without that line the seed fails quietly and Certify makes
   its own keys (found by Navish)
3. Create `docker-compose/docker-compose.override.yaml`:
   ```yaml
   services:
     database:
       volumes:
         - ./keys_seed.local.sql:/docker-entrypoint-initdb.d/zz_keys_seed.sql
   ```
4. `docker-compose down -v && docker-compose up -d`
5. Check that `/.well-known/did.json` matches the published one

## What we found

Things about Certify 0.14 that cost us time, for anyone integrating against it:

- **Pre-authorized claims go into the access token.** Certify copies every claim from
  `/pre-authorized-data` into the token's `sub`. With a photo claim the token is about
  20 KB, and Tomcat's default 8 KB header limit then rejects the credential request with
  a bare HTML 400. `certify-preauth.properties` raises the limit to 64 KB.
- **Offers are checked against the config's declared claims.** `/pre-authorized-data`
  refuses any claim not declared for the credential config (`unknown_claims`). JSON-LD
  and mDoc configs declare them in `credential_subject`, SD-JWT configs in
  `sd_jwt_claims`. Our `FarmerCredential` used to declare only four fields (one of them a
  stale `phone`); `certify_init.sql` now declares all of them.
- **The offer cache isn't declared by default.** Without `credentialOfferCache` in
  `mosip.certify.cache.names`, `/pre-authorized-data` fails with `credentialOfferCache not
  available`.
- **One trusted token issuer per instance**, see "Why two" above.
- **No clock leeway on `iat`** (verify/docs/FINDINGS.md F12): `issuance_flow.py` waits
  until the token's `iat` has passed before asking for the credential.
- **The first credential after a restart is slow** under emulation on Apple Silicon (the
  first signing does key work), so the credential request has a 90 second timeout.
- **MOSIP Collab's Certify moved its metadata** to `/v1/certify/.well-known/openid-credential-issuer`;
  the `/v1/certify/issuance/.well-known/...` address in the wallet's sample `Mock` issuer
  entry now returns 404.

## Architecture

This component is one piece of the larger playground — see the top-level
project README and architecture diagram for how Certify fits with the
Playground BFF, Wallet, and Verify pieces.
