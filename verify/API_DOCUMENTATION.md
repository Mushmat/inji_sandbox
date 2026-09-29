# verify/ API documentation

Two layers: the Inji Verify endpoints the flow calls, and the Python / HTTP API this folder exposes.

## 1. Inji Verify 0.18.2 endpoints used

Base: `INJI_VERIFY_URL` (default `http://localhost:8080/v1/verify`). Taken from the verify-service
source at tag v0.18.2.

### Create a presentation request (verifier backend)

`POST /vp-request`

```json
{ "clientId": "inji-sandbox-playground", "nonce": "<random>", "presentationDefinition": { ... } }
```

`201`:

```json
{
  "transactionId": "…", "requestId": "…", "expiresAt": 1790000000000,
  "authorizationDetails": {
    "responseType": "vp_token", "responseMode": "direct_post", "clientId": "…", "nonce": "…",
    "presentationDefinition": { ... }, "responseUri": "<INJI_VP_SUBMISSION_BASE_URL>/vp-submission/direct-post",
    "acceptVPWithoutHolderProof": false, "responseCodeValidationRequired": false
  }
}
```

The wallet link is built like the official `@mosip/react-inji-verify-sdk`:
`openid4vp://authorize?client_id&state=<requestId>&response_mode&response_type&nonce&response_uri&presentation_definition&client_metadata`
(or `client_id` + `request_uri` if Inji Verify returns a `requestUri`).

### Wallet submission

`POST /vp-submission/direct-post`, `application/x-www-form-urlencoded`:
`vp_token`, `presentation_submission`, `state` (= requestId). Or `error` / `error_description`.

- JSON-LD: `vp_token` is the VP JSON. `proof.challenge` must equal the nonce and `proof.domain` the
  client id, else `400 {"errorCode":"NONCE_VALIDATION_FAILED" | "CLIENT_ID_VALIDATION_FAILED"}`.
- SD-JWT: `vp_token` is `<issuer-jwt>~<disclosure>~…~<kb-jwt>`.
- `presentation_submission`:
  `{"id","definition_id","descriptor_map":[{"id","format":"ldp_vp","path":"$","path_nested":{"format":"ldp_vc","path":"$.verifiableCredential[0]"}}]}`
  (SD-JWT: `{"format":"vc+sd-jwt","path":"$"}`).

### Status (long poll)

`GET /vp-request/{requestId}/status` → `{"status": "ACTIVE" | "VP_SUBMITTED" | "EXPIRED"}`. Held open up to
`INJI_VP_REQUEST_LONG_POLLING_TIMEOUT` (55 s).

### Result

`POST /v2/vp-results/{transactionId}` with `{"includeClaims": true, "skipStatusChecks": false, "statusCheckFilters": []}`:

```json
{ "transactionId": "…", "allChecksSuccessful": true,
  "credentialResults": [ { "verifiableCredential": "…", "holderProofCheck": {"valid": true, "error": null},
      "schemaAndSignatureCheck": {"valid": true, "error": null}, "expiryCheck": {"valid": true},
      "statusCheck": [], "claims": { … } } ] }
```

Errors: `400 TOKEN_MATCHING_FAILED | INVALID_VP_TOKEN`, `404 INVALID_TRANSACTION_ID | NO_VP_SUBMISSION`,
`500 VP_VERIFICATION_FAILED | VP_WITHOUT_PROOF`. If `/v2/…` returns 404/405 without an `errorCode`, the
client falls back to v1: `GET /vp-result/{transactionId}` → `{"vpResultStatus": "SUCCESS"|"FAILED", "vcResults": [{"vc", "verificationStatus"}]}`.

Mapped to one word: `VALID`, `INVALID`, `EXPIRED`, `ERROR`, or `REJECTED` (refused at submission; counts as INVALID).

## 2. Python API

### `presentation_flow.run_presentation(vc_format, scenario="none", source=None, wallet=None, verifier=None) -> dict`

Never raises. `vc_format`: `ldp_vc` | `vc+sd-jwt` (`mso_mdoc` returns an explanation).
`scenario`: `none` | `altered` | `replay` | `wrong_type` | `forged_issuer`. `source`: `wallet` (use what it holds),
`certify` (run Chirayu's flow first), `test` (offline test issuer); default: `wallet` if it holds one, else `certify`.

```text
{
  ok, error, format, scenario, scenario_info {label, expected, explain},
  steps: [ {name, actor: verifier|wallet|issuer|playground, method, url, status, ok, request, response, note?} ],
  session: {transaction_id, request_id, client_id, nonce, response_uri, presentation_definition, authorization_request_uri, expires_at},
  presentation: {what the wallet sent: proof type / disclosed + withheld claims / KB-JWT, altered?},
  verifier_result: {status, detail, checks: [{label, ok, detail}], claims, credentials},
  playground_checks: [{id, label, ok: true|false|null, detail, ref}],
  outcome: {expected, result, verdict: PASS|FAIL|ERROR, explanation},
  suspected_gaps: [{summary, failed_checks, finding: ["F2"] | null}]
}
```

Steps from Chirayu's issuance flow keep his fields; they get `actor: "issuer"` and an `Issuance:` prefix.

### Phone mode

`start_phone_session(vc_format, scenario="none") -> {ok, id, authorization_request_uri, qr (SVG data URL), response_uri, steps, hint}`
`poll_phone_session(id) -> {ok, done: false, status}` until `done: true` with the same fields as above.

### Wallet (`wallet.HolderWallet(directory=None)`)

`did`, `public_jwk`, `receive_from_certify(fmt)` (Chirayu's result dict + `wallet`), `receive_from_test_issuer(fmt)`,
`import_credential(fmt, credential)`, `summary()`, `read_request(uri)`, `match(request, fmt)`,
`build_presentation(request, fmt, descriptor, alter=False)`, `submit(log, request, presentation)`, `clear()`.

### Checks (`checks.run_checks(vc_format, session, submitted=None, verifier_credentials=None)`)

| id | check | spec |
|---|---|---|
| `state`, `submission` | response belongs to this session / definition | OpenID4VP, DIF PE |
| `holder_signature` | VP proof (JsonWebSignature2020) verifies | VC Data Integrity |
| `challenge`, `domain` | VP bound to this nonce and client_id | OpenID4VP |
| `holder_binding` | presenter's key = `credentialSubject.id` | VC Data Model |
| `issuer_signature` | Ed25519Signature2020 via the verification method / SD-JWT issuer JWS (x5c, else kid / iss) | VC Data Integrity, SD-JWT |
| `issuer_key_binding` | the signing key belongs to the issuer (JSON-LD: verification method's DID is the issuer; SD-JWT: key is one of the issuer's published keys) | VC Data Integrity, SD-JWT VC |
| `did_published` | hosted did.json has Certify's current keys (only when the issuer signature fails) | did:web |
| `disclosures` | every disclosure matches a signed digest | SD-JWT |
| `kb_signature`, `kb_nonce`, `kb_aud`, `kb_sd_hash`, `kb_fresh` | key-binding JWT | SD-JWT |
| `expiry` | not expired | VC Data Model, SD-JWT VC |
| `constraints` | credential meets the presentation_definition | DIF PE |

## 3. Demo server (port 5002)

| method | path | body | returns |
|---|---|---|---|
| GET | `/healthz` | | `{"status":"ok"}` |
| GET | `/api/status` | | Inji Verify / Certify reachability, whether the patch is applied, scenarios |
| GET | `/api/wallet` | | `HolderWallet.summary()` |
| POST | `/api/wallet/receive` | `{format, source: "certify"|"test"}` | issuance steps + `wallet_summary` (502 on failure) |
| POST | `/api/wallet/clear` | | empty wallet summary |
| POST | `/api/present` | `{format, scenario}` | `run_presentation` result (502 if `ok` is false) |
| POST | `/api/present/phone` | `{format, scenario}` | `start_phone_session` result |
| GET | `/api/present/phone/<id>` | | `poll_phone_session` result |
