# Playground API

This documents the existing BFF at `96d38b0`. The default address is `http://localhost:5050`; `/docs` provides interactive OpenAPI documentation and `/openapi.json` its schema. Component APIs have separate [Certify](../certify/API_DOCUMENTATION.md) and [Verify](../verify/API_DOCUMENTATION.md) documentation.

## Start and observe a run

```http
POST /api/runs
Content-Type: application/json

{"issuer":"certify","wallet":"inji_web","verifier":"inji_verify","format":"ldp_vc","scenario":"none"}
```

HTTP 202 returns the run and its `id`. Poll `GET /api/runs/{id}` while status is `running` or `waiting`. Interactive runs provide an `awaiting` object with instructions, wallet link or QR. After downloading in Inji Web, `POST /api/runs/{id}/continue` starts presentation. In this version continuation records the user's confirmation, without independently proving the download or capturing Mimoto's internal issuance traffic.

`POST /api/compatibility` accepts the same fields and returns HTTP 200 with `runnable`, `blockers` and `limits`; an unsupported combination of valid field values returns `runnable: false`. Invalid request fields return HTTP 422. `POST /api/runs` also returns HTTP 422 when the requested combination is unsupported, or HTTP 409 when a run is busy or services are still starting. An invalid continuation returns HTTP 409 from `POST /api/runs/{id}/continue`.

| Field | Values |
|---|---|
| `issuer` | `certify_preauth`, `certify`, `test_issuer` |
| `wallet` | `playground_wallet`, `inji_web`, `browser_wallet` |
| `verifier` | `inji_verify`, `playground_verifier` |
| `format` | `ldp_vc`, `vc+sd-jwt`, `mso_mdoc` |
| `scenario` | `none`, `altered`, `replay`, `wrong_type`, `forged_issuer`, `expired` |

These are not freely interchangeable. `/api/catalog` and `/api/compatibility` describe supported combinations. Inji Web uses the eSignet issuer and cannot present SD-JWT in the pinned release. Browser-wallet runs present an already-held credential; the selected issuer does not issue into that external wallet.

## Runs and reports

| Endpoint | Behavior |
|---|---|
| `GET /api/health` | Service readiness and published-DID key agreement |
| `GET /api/catalog` | Participants, versions, formats and scenarios |
| `GET /api/runs?limit=500` | Recent summaries, newest first |
| `GET /api/runs/{id}` | Run details, steps, checks and timings |
| `POST /api/runs/{id}/cancel` | End an active run |
| `GET /api/report.md` | Markdown compatibility matrix, flow health and run summaries |
| `GET /api/report.md?ids=a,b` | Report restricted to selected IDs |
| `GET /api/wallet` | Scripted holder's stored credential summaries |
| `DELETE /api/runs` | Delete history; the UI requests confirmation |

`outcome.result` is the verifier answer; `outcome.verdict` compares it with the scenario expectation. `INVALID` can correspond to `PASS`. Raw scripted traces may include token material; publish summary reports using mock data instead of token-bearing run documents.

## Matrix, subject and device wallets

`POST /api/matrix` accepts `{"preset":"quick"}` for honest automated combinations or `{"preset":"full"}` for tamper cases too. `GET /api/matrix` returns progress, run IDs, retries, cancellation and errors. `POST /api/matrix/cancel` requests cancellation. Interactive wallets are excluded from unattended runs.

`GET /api/identity` reads the mock subject. `PUT /api/identity` accepts `{"fields":{"fullName":"Demo Farmer"}}`; unknown fields and invalid values are refused. `POST /api/identity/reload` restarts the eSignet Certify to load saved CSV data. `GET /api/identity/status` reports progress. The preauthorized issuer uses the supplied subject on its next request.

The Playground verifier API is under `/verifier/v1/verify`. Browser-wallet runs use `POST /api/runs/{id}/dc-api` with `{"origin":"http://localhost:5050"}` to prepare the Digital Credentials API request. Live acceptance needs a supporting wallet and an already-held Farmer credential; simulated wallet-response tests do not establish device interoperability.
