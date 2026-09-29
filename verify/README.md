# verify/ — Present & Verify (FR4)

The second half of the round trip. `certify/` (Chirayu) issues a Farmer credential from Inji Certify;
`verify/` takes that credential into a holder wallet, presents it to **Inji Verify 0.18.2** over
**OpenID4VP**, and shows the result next to the playground's own checks.

```
 Inji Certify ──(certify/ issuance flow)──▶ holder wallet ──OpenID4VP──▶ Inji Verify
                                              (wallet.py)                  │
                                                                           ▼
                        playground: Inji Verify's verdict  vs  our own checks  → PASS / FAIL / suspected gap
```

Same shape as `certify/`: `scripts/` (flow, CLI, tests), `demo-ui/` (Flask, port 5002),
`docker-compose/` (the Inji service), plus `API_DOCUMENTATION.md` and `docs/FINDINGS.md`.

## In plain words

1. **The verifier asks.** Our script plays the relying party's backend. It asks Inji Verify to open a
   session (`POST /vp-request`) saying "I want a FarmerCredential" (a *presentation definition*) and a
   random *nonce*. Inji Verify returns an `openid4vp://` link, which is what a QR code would contain.
2. **The wallet answers.** The built-in wallet reads the link, checks it has a matching credential, and
   builds a *presentation*: the credential plus the holder's signature over the nonce, so it can't be
   reused elsewhere. For SD-JWT it reveals only `farmerID` (the one claim asked for) and adds a
   key-binding JWT. It posts this to Inji Verify's `response_uri`.
3. **The verifier decides.** Our script waits for Inji Verify to receive it, then fetches the verdict
   (`POST /v2/vp-results/{transactionId}`): holder proof, issuer signature, expiry, status.
4. **The playground double-checks.** `checks.py` re-does the checks independently (signatures, nonce,
   holder binding, SD-JWT digests, the request's constraints). If Inji Verify says VALID where a check
   failed, that's a **suspected gap**, linked to `docs/FINDINGS.md`.

### Scenarios (FR4 negative tests)

| scenario | what happens | should be |
|---|---|---|
| `none` | honest presentation | VALID |
| `altered` | wallet changes `farmerID` after issuance, signs the presentation normally | INVALID |
| `replay` | presentation from session 1 re-sent to session 2 (old nonce) | INVALID |
| `wrong_type` | verifier asks for `LandOwnershipCredential`; wallet sends FarmerCredential anyway | INVALID |
| `forged_issuer` | someone makes a credential naming Certify as issuer, signed with their own key | INVALID |
| `expired` | a genuine credential whose expiry date has passed (signed by the test issuer, since Certify can't issue one) | VALID BUT EXPIRED |

**One command on Windows:** `.\verify\tools\start-demo.ps1 -Python <venv python> -VerifyPort 8082 -WalletCompose .\wallet\docker-compose`
starts the https tunnel, Inji Verify, the Inji Web trusted-verifier entry and the demo page.

**Live results (2026-09-29):** Inji Verify gets honest, altered and JSON-LD replay right, and wrongly
accepts SD-JWT replay (F3), wrong type (F2) and forged issuer (F10). Full table in `docs/FINDINGS.md`.

The *expired* scenario uses the offline test issuer: Certify decides the expiry, and a credential can't be made
to expire without breaking its signature. mDoc is shown but disabled: Inji Verify 0.18.2 can't receive it
over OpenID4VP (FINDINGS M1).

## Setup

**1. Put `verify/` next to `certify/`** in the repo (the wallet imports
`../certify/scripts/issuance_flow.py`; or set `CERTIFY_SCRIPTS_DIR`).

**2. Apply the two small patches to Chirayu's issuance flow** (`patches/`, details in `patches/README.md`).
- `issuance_flow_holder_key.patch`: a presentation must be signed with the key the credential was issued
  to, and `run_issuance()` makes a throwaway key and discards it. Adds an optional `holder_key` argument;
  without it, everything behaves exactly as before.
- `issuance_flow_iat_wait.patch`: Certify rejects the access token if the computer's clock is even a
  second behind Collab's (FINDINGS F12). Waits until the token's `iat` has passed before asking for the
  credential. Also sync your clock (Windows: Settings → Time & language → Date & time → Sync now).

```bash
git apply verify/patches/issuance_flow_holder_key.patch     # from the repo root
git apply --ignore-whitespace verify/patches/issuance_flow_iat_wait.patch
```

**3. Start the services**

```bash
docker network create mosip_network          # once (certify/ uses it too)
(cd certify/docker-compose && docker compose up -d)   # Certify on 8090
(cd verify/docker-compose && docker compose up -d)    # Inji Verify on 8080
```

Port 8080 already taken? Pick another and tell both sides:
`VERIFY_PORT=8082 VERIFY_PUBLIC_URL=http://localhost:8082 docker compose up -d`, then run the scripts and
demo UI with `INJI_VERIFY_URL=http://localhost:8082/v1/verify` (PowerShell: `$env:INJI_VERIFY_URL=...`).

**4. Install and run**

```bash
cd verify/scripts
pip install -r requirements.txt
python3 test_presentation_flow.py ldp_vc none --source certify   # issue + present, JSON-LD
python3 test_presentation_flow.py "vc+sd-jwt" all                # every scenario, summary table
```

Or the browser demo: `cd verify/demo-ui && pip install -r requirements.txt && python3 server.py`,
then open http://localhost:5002.

No Certify handy (Collab eSignet down, etc.)? `--source test` (or *Use offline test issuer* in the UI)
issues a look-alike credential from a local `did:key` test issuer. It is labelled as such everywhere.

## Presenting from Inji Web (Navish's wallet)

Tested live 2026-09-29: JSON-LD from Inji Web 0.17 → Inji Verify comes back **VALID**. Inji Web can't present
SD-JWT (FINDINGS W5), so SD-JWT is presented with the built-in wallet. What it takes:

1. **An https address for Inji Verify.** Inji Web only posts to `https://` without a port (W2):
   ```bash
   docker run -d --name inji-verify-tunnel --network mosip_network cloudflare/cloudflared:latest \
     tunnel --no-autoupdate --url http://inji-verify-verify-service-1:8080
   docker logs inji-verify-tunnel     # note the https://<random>.trycloudflare.com address
   VERIFY_PORT=8082 VERIFY_PUBLIC_URL=https://<random>.trycloudflare.com docker compose up -d   # in verify/docker-compose
   ```
   The address changes whenever the tunnel restarts; repeat the last line and step 2 then.
2. **Our verifier in the wallet's `mimoto-trusted-verifiers.json`**, then restart `mimoto-service`:
   ```json
   {"client_id": "inji-sandbox-playground", "redirect_uris": [],
    "response_uris": ["https://<random>.trycloudflare.com/v1/verify/vp-submission/direct-post"],
    "allow_unsigned_request": true}
   ```
   `allow_unsigned_request` is required (W6).
3. **Certify must accept Ed25519 proofs** (`patches/certify_add_ed25519_proof_alg.sql`), and cards downloaded
   before that must be downloaded again (W3/W4).
4. **Start the demo UI** with `INJI_WEB_URL=http://localhost:3004` (default) and, so the built-in wallet can still
   post from the host, `WALLET_URL_REWRITES=https://<random>.trycloudflare.com=http://localhost:8082`.
5. Sign in to Inji Web, then on the demo page: **Present with a real wallet** → **Open in Inji Web** → consent.
   In this mode the playground only sees the credential Inji Verify returns, so nonce / holder checks show "not run".

If you also run Navish's wallet compose, start it with its own project name (`docker compose -p inji-wallet up -d`):
it lives in a folder called `docker-compose` like Certify's, and the two would otherwise share volume names.

## Tests

```bash
cd verify/scripts
ALLOW_REMOTE_CONTEXTS=0 python3 -m unittest discover -s tests -v   # 31 offline tests (~1 s); the 4 live ones skip
python3 -m unittest tests.test_presentation_live -v                 # needs Certify + Inji Verify
```

The offline suite needs no Docker or network. It covers:
- **Signatures made by other implementations** (`tests/fixtures/external_signed_vp.json`): a VC signed by
  Digital Bazaar's jsonld-signatures (Ed25519Signature2020) inside a VP signed with JsonWebSignature2020
  by an independent signer. Our verifier must accept both, and reject them when tampered.
- DID resolution for `did:jwk`, `did:key`, and `did:web` using Chirayu's actual `docs/did.json` keys.
- SD-JWT: nested `_sd` (how Certify puts `farmerID`), selective disclosure, KB-JWT, tampering.
- The request link matches the official Inji Verify SDK's format; result mapping for v2 and v1.
- The wallet's key handling, and a clear error if the patch isn't applied.
- The whole flow over HTTP against `tests/fake_inji_verify.py`, a **model** of verify-service 0.18.2
  built from its source (same paths, fields, error codes and the same gaps). It predicts the live
  results; the live test is what confirms them.

The live test prints a results table: paste it into `docs/FINDINGS.md`.

## Configuration

| variable | default | what |
|---|---|---|
| `INJI_VERIFY_URL` | `http://localhost:8080/v1/verify` | verify-service base URL |
| `VERIFY_CLIENT_ID` | `inji-sandbox-playground` | client_id our relying party uses |
| `VERIFY_PUBLIC_URL` | `http://localhost:8080` | (compose) base of `response_uri`; set to a LAN IP for phones |
| `VERIFY_WALLET_DIR` | `verify/.wallet` | holder key + credentials (git-ignored; delete to reset) |
| `CERTIFY_SCRIPTS_DIR` | `../certify/scripts` | where Chirayu's `issuance_flow.py` is |
| `CERTIFY_DID_DOCUMENT_URL` | `http://localhost:8090/v1/certify/.well-known/did.json` | used to spot a stale hosted `did.json` |
| `DID_WEB_OVERRIDES` | empty | `did:web:x=http://...did.json` to resolve a DID from a local copy (our checks only) |
| `ALLOW_REMOTE_CONTEXTS` | `1` | `0` = only the bundled JSON-LD contexts (offline) |
| `VERIFY_LONG_POLL_SECONDS` | `70` | how long to wait for a wallet |

## Phone wallets

*Present with a phone wallet (QR)* shows the `openid4vp://` link as a QR code and waits. Two things
must hold: the phone can reach `response_uri` (set `VERIFY_PUBLIC_URL` to your computer's LAN address
and restart the verify-service container), and the wallet app accepts this verifier (Inji Wallet
may only trust verifiers it has been configured with). In phone mode we never see the presentation
itself, so nonce and holder-proof checks are shown as "not run"; issuer signature, expiry and
constraints are still checked on the credential Inji Verify returns.

## Files

```
verify/
  scripts/
    presentation_flow.py   run_presentation(format, scenario) and phone mode; never raises
    wallet.py              holder wallet: key, receive from Certify, build + submit presentations
    verifier_client.py     Inji Verify REST client (request, link, long poll, results v2/v1)
    checks.py              the playground's independent checks
    pex.py                 presentation definitions (within what Inji Verify keeps, F4)
    sdjwt.py               SD-JWT parse / nested disclosures / key binding
    jsonld_proofs.py       JsonWebSignature2020 + Ed25519Signature2020 (URDNA2015)
    did_resolver.py        did:jwk, did:key, did:web
    test_issuer.py         offline did:key issuer with Certify's credential shapes
    steps.py               step log (same fields as certify/ steps)
    contexts/              bundled JSON-LD contexts
    test_presentation_flow.py   CLI
    tests/                 offline + live tests, fixture, model of Inji Verify
  demo-ui/                 Flask server + single-page UI (port 5002)
  docker-compose/          verify-service 0.18.2 + Postgres 5434, on mosip_network
  patches/                 holder-key patch for certify/scripts/issuance_flow.py
  docs/FINDINGS.md
  API_DOCUMENTATION.md
```
