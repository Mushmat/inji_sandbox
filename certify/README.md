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

## Known limitation

`did-url` (in `docker-compose/config/certify-csvdp-farmer.properties` and
`certify_init.sql`) currently points at a placeholder hostname from the
upstream sample, not a host we control. The issuer works and signs correctly
regardless — this only matters once a Verifier needs to actually resolve and
check our DID, which requires hosting it somewhere public (GitHub Pages is
the plan). Not blocking issuance testing.

## Architecture

This component is one piece of the larger playground — see the top-level
project README and architecture diagram for how Certify fits with the
Playground BFF, Wallet, and Verify pieces.
