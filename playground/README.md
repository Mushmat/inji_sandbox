# Playground

The part the jury sees: one page to run issue → hold → present → verify across the
three Inji modules, with every protocol message visible.

- `bff/` is the backend (Python, FastAPI). It is the only thing the UI calls.
- `web/` is the UI (React + TypeScript, Vite, Tailwind).

Start the Inji stack first (`python integration/stack.py up`, see the root README).

## Run

```bash
cd web && npm install && npm run build && cd ..
python bff/main.py                # http://localhost:5050
```

While working on the UI, run `npm run dev` in `web/` instead of building. It serves on
http://localhost:5173 with hot reload and forwards `/api` to the BFF on 5050.

## How a run works

`bff/runner.py` takes an issuer, wallet, verifier, format and scenario and runs the
cycle in a background thread. The UI polls `GET /api/runs/{id}` and shows steps as
they arrive.

1. **Issue.** With Certify, the wallet gets a credential offer, reads Certify's
   metadata, logs in through eSignet and requests the credential
   (`certify/scripts/issuance_flow.py`). With the test issuer, the credential is
   signed locally with a `did:key`.
2. **Hold.** The Playground wallet stores it, bound to its own EC P-256 key.
3. **Present.** The BFF, acting as the relying party, asks Inji Verify for a
   presentation request. The wallet answers with a signed `vp_token` over
   `direct_post` (`verify/scripts/presentation_flow.py`).
4. **Verify.** Inji Verify's result is fetched and compared with the playground's
   own checks (`verify/scripts/checks.py`). Expected result, actual result and
   verdict go into the report.

With **Inji Web** as the wallet, a person does the wallet's part: the run pauses,
shows what to do, and continues when Inji Verify reports back. Mimoto's own
traffic isn't visible from outside, so those runs show the issuer's and
verifier's side of the exchange.

Combinations that can't work are refused with the reason (`bff/catalog.py`).
Combinations that run but can't finish, like presenting mDoc to Inji Verify, are
recorded as UNSUPPORTED with the reason, so the gap shows up in the report.

## API

Interactive reference with request and response schemas: http://localhost:5050/docs

| Method | Path | What it does |
|---|---|---|
| GET | `/api/health` | Status of each module, and whether Certify's keys match the published DID |
| GET | `/api/catalog` | Issuers, wallets, verifiers, formats, scenarios, module versions |
| POST | `/api/compatibility` | Whether a combination can run, and its known limits |
| POST | `/api/runs` | Start a run. `409` if one is already in progress |
| GET | `/api/runs` | Run history, newest first |
| GET | `/api/runs/{id}` | One run with every step |
| POST | `/api/runs/{id}/continue` | Inji Web runs: the card is downloaded, go on to the presentation |
| POST | `/api/runs/{id}/cancel` | Stop a run |
| DELETE | `/api/runs` | Clear the history |
| GET | `/api/report.md` | The interoperability report as markdown |
| GET | `/api/wallet` | What the Playground wallet holds |

Runs are stored in `playground/.data/runs.sqlite3`, and the Playground wallet's key
and credentials in `playground/.data/wallet/`. Both are gitignored; delete the
folder to start fresh.
