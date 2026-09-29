# Playground

The part the jury sees: one page to run issue → hold → present → verify across the
Inji modules and our own non-Inji ones, with every protocol message visible.

- `bff/` is the backend (Python, FastAPI). It's the only thing the UI calls, and it
  also hosts the Playground verifier.
- `web/` is the UI (React + TypeScript, Vite, Tailwind).
- `run_matrix.py` runs the test matrix from the command line, for CI.

## Run

Normally `python integration/stack.py up` builds and starts all of this in a container
(see the root README). To work on it from source instead:

```bash
python integration/stack.py up --no-playground   # everything else
python -m venv .venv && source .venv/bin/activate && pip install -r playground/bff/requirements.txt
cd playground/web && npm install && npm run build && cd ../..
python playground/bff/main.py                     # http://localhost:5050
```

For UI work, `npm run dev` in `web/` serves on http://localhost:5173 with hot reload and
forwards `/api` to the BFF.

## Who plays each role

| Role | Options |
|---|---|
| Issuer | Inji Certify with pre-authorized code (Certify writes the offer); Inji Certify with eSignet login (what Inji Web uses); a did:key test issuer (non-Inji) |
| Wallet | Playground wallet (scripted, can misbehave on purpose); Inji Web (you drive it); a wallet on this device, through the Digital Credentials API |
| Verifier | Inji Verify; the Playground verifier (non-Inji) |

Combinations that can't work are refused with the reason (`bff/catalog.py`).
Combinations that run but can't finish, like presenting mDoc to Inji Verify, are
recorded as UNSUPPORTED with the reason, so the gap shows up in the report.

## How a run works

`bff/runner.py` runs the cycle in a background thread and the UI polls for steps.

1. **Issue.** Pre-authorized: the issuer's back office sends the person's details to
   Certify, Certify returns a credential offer, and the wallet redeems its code for a
   token and the credential. eSignet login: the wallet logs in through Collab's mock
   eSignet and requests the credential. Test issuer: signed locally with a `did:key`.
2. **Hold.** The Playground wallet stores it, bound to its own EC P-256 key.
3. **Present.** The BFF, as the relying party, opens a request at the verifier. The
   wallet answers with a signed `vp_token` over `direct_post`.
4. **Verify.** The verifier's result is compared with the expected outcome of the
   scenario, and with the independent checks in `verify/scripts/checks.py`.

With Inji Web, a person does the wallet's part: the run pauses, shows what to do, and
continues when the verifier reports back. Mimoto's own traffic isn't visible from
outside, so those runs show the issuer's and verifier's side of the exchange.

## The Playground verifier

`bff/verifier_service.py` is an OpenID4VP relying party written from the specs. To a
wallet it is plain OpenID4VP: an `openid4vp://` request with a `presentation_definition`
and a nonce, answered by `direct_post`. Its back end has the same four calls as Inji
Verify's verify-service, so the same relying-party client drives either one and the
comparison is like for like. It refuses a presentation signed for another request's
nonce, for both formats, and its verdict comes from `verify/scripts/checks.py`, which
also checks the presentation_definition and that the signing key is the issuer's. Those
are the three things Inji Verify 0.18.2 skips (FINDINGS F2, F3, F10).

It also takes answers through the browser's **Digital Credentials API** (FR13). The page
calls `navigator.credentials.get` with two requests: OpenID4VP 1.0 with a DCQL query,
and the earlier draft with a `presentation_definition`. The wallet answers one of them,
bound to the page's origin (`origin:http://localhost:5050`), and the page posts the answer
to the verifier.

## Test matrix (FR14)

The Report tab's test matrix, and `python playground/run_matrix.py [--full]`, run every
automated combination one after another: 14 runs for quick (honest runs), 74 for full
(every tamper scenario). The script writes the report and exits 1 if any run errors
(`--strict`: also if a verifier gives the wrong answer). `.github/workflows/nightly-matrix.yml`
does this every night on a GitHub runner.

## API

Interactive reference with request and response schemas: http://localhost:5050/docs

| Method | Path | What it does |
|---|---|---|
| GET | `/api/health` | Status of each module and tunnel, and whether Certify's keys match the published DID |
| GET | `/api/catalog` | Issuers, wallets, verifiers, formats, scenarios, module versions |
| POST | `/api/compatibility` | Whether a combination can run, and its known limits |
| POST | `/api/runs` | Start a run. `409` if one is already in progress |
| GET | `/api/runs` | Run history, newest first |
| GET | `/api/runs/{id}` | One run with every step |
| POST | `/api/runs/{id}/continue` | Inji Web runs: the card is downloaded, go on to the presentation |
| POST | `/api/runs/{id}/dc-api` | Digital Credentials API runs: build the request for the page's origin |
| POST | `/api/runs/{id}/cancel` | Stop a run |
| DELETE | `/api/runs` | Clear the history |
| GET | `/api/report.md` | The interoperability report as markdown (`?ids=` for a subset) |
| GET, POST | `/api/matrix` | Test matrix progress / start (`{"preset": "quick" \| "full"}`) |
| POST | `/api/matrix/cancel` | Stop the matrix after the current run |
| GET, PUT | `/api/identity` | The mock person credentials are issued for / change it |
| GET | `/api/identity/status` | Progress of the eSignet Certify's restart after a change |
| GET | `/api/wallet` | What the Playground wallet holds |
| POST | `/verifier/v1/verify/vp-request` | Playground verifier: open a presentation request |
| GET | `/verifier/v1/verify/vp-request/{id}/status` | Long poll until the wallet answers |
| POST | `/verifier/v1/verify/vp-submission/direct-post` | The wallet's answer (OpenID4VP `direct_post`) |
| POST | `/verifier/v1/verify/dc-api/{id}/response` | The wallet's answer through the Digital Credentials API |
| POST | `/verifier/v1/verify/v2/vp-results/{txn}` | The verdict |

The credential subject follows these rules (`bff/identity.py`, mirrored in the UI): Farmer
ID exactly 9 digits (MOSIP doesn't define one; 9 matches the data we started from),
mobile 10 digits starting 6–9, PIN code 6 digits, a real date of birth, and the photo as
an image.

Runs are stored in `playground/.data/runs.sqlite3`, and the Playground wallet's key and
credentials in `playground/.data/wallet/`. Both are gitignored; delete the folder to
start fresh.

## Tests

```bash
python -m unittest discover -s playground/bff/tests -p "test_*.py"
cd playground/web && npm test
```

The backend suite runs offline in a few seconds. It starts the BFF on a free port and
runs every tamper scenario, both formats, against the Playground verifier over real HTTP,
plus the Digital Credentials API answers, the compatibility rules, the person-data rules
and the report.
