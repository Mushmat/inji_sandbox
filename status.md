# Status — Chirayu — Issuer (Inji Certify)

Last updated: 2026-09-24

## Summary

The issuer side is done and tested — Inji Certify is running locally via
Docker Compose, issuing three credential formats (JSON-LD, SD-JWT, mDoc/mDL)
through a real, verified OpenID4VCI flow. FR1 (issuer side), FR3, FR6, and
FR9 (good-to-have third format) are all complete. There's also a demo UI to
show it working without touching a terminal.

## What's done

**Issuer running, all three formats working**
- Inji Certify + Postgres + Nginx via Docker Compose, with real health
  checks (not just "container started")
- Three credential formats, all seeded automatically on a fresh database:
  - `FarmerCredential` — W3C VC JSON-LD, `Ed25519Signature2020`
  - `FarmerCredentialSdJwt` — SD-JWT VC, selective disclosure on `farmerID`
  - `MobileDrivingLicense` — ISO 18013-5 mDoc/mDL, CBOR + COSE_Sign1, EC
    P-256 holder key (the one place holder-key type actually differs by
    format — COSE only supports EC, not RSA)
- Full pre-authorized-code OpenID4VCI flow tested end-to-end against MOSIP
  Collab's public mock eSignet (no account/login needed on our side — Collab
  ships a public demo client for exactly this) — real signed credentials
  come back, not mocked responses

**Backend quality**
- Every network call has a timeout and a proper exception boundary — a
  network drop or slow response returns a clean error, never a crash
- 14 automated assertions (`test_credential_shape.py`) checking actual
  credential structure per format, not just HTTP status codes
- Identity data (the mock person credentials get issued for) is editable
  live from the UI, including a real device-camera photo capture — no more
  hand-editing a CSV

**Demo UI** (`certify/demo-ui/`)
- Pick a format, issue a credential, watch the protocol steps live, see the
  result rendered per format (claims table / decoded SD-JWT payload /
  decoded mDoc claims)
- Identity editor only shows the fields the selected format actually uses
  (mDoc needs 3 fields, JSON-LD/SD-JWT use the full profile)
- Saving identity data restarts Certify in the background with live
  progress — a real constraint (the bundled plugin caches data at startup,
  confirmed by reading its source), not a bug

**Docs**
- `certify/README.md` — setup, prerequisites, how to run everything
- `certify/API_DOCUMENTATION.md` — every endpoint we use, plus every real
  gotcha hit along the way (proof JWT claims, OAuth scope quirks, the EC vs
  RSA holder key issue) — useful for anyone integrating against this later

## Not done yet

- **DID hosting** — `did-url` points at `did:web:mushmat.github.io:inji_sandbox`
  and the DID document is at `/docs/did.json` on `feature/certify-issuer`.
  Served by GitHub Pages from that branch's `/docs` folder once the repo is
  public. Anyone running their own Certify needs the shared keystore to
  match it — see "Running this issuer on another machine" in
  `certify/README.md`.
- **BFF / wallet / verifier integration** — deliberately not started.
  Connecting our issuer to Inji Wallet needs one config entry added
  (`mimoto-issuers-config.json`, already in our `docker-compose/config/`
  folder, ready to fill in with our issuer's details whenever the wallet
  piece exists). The Playground BFF itself should wait until all three
  pipelines exist — building it against only one real backend means
  guessing at the other two APIs and likely redoing it later.

## For whoever picks up integration later

Everything needed to plug into this issuer is in
`certify/API_DOCUMENTATION.md` — the exact endpoints, request/response
shapes for all three formats, and the specific gotchas (missing `iat` on
the proof JWT, OAuth scope needing to match what's registered on the auth
server, EC vs RSA holder keys) that cost real debugging time and are worth
not re-discovering.

## Try it yourself

```bash
cd certify/docker-compose && docker-compose up -d
cd ../demo-ui && source ../.venv/bin/activate && python3 server.py
```
Open `http://localhost:5001`. Full setup instructions in `certify/README.md`.
