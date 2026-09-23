# Issuer Demo UI

A page for showing the issuer piece working without reading terminal output
or hand-editing a CSV file. Not the team's playground UI — that's a
separate, bigger piece someone else owns. This is for showing teammates
(and the pitch/demo video) that the issuer side is real and working, across
all three credential formats.

- Edit the identity credentials get issued for, right from the page.
- Pick a format (JSON-LD, SD-JWT, or mDoc/mDL) and issue a real credential.
- Watch the protocol steps as they happen — click any step to see its raw
  response.
- See the result rendered per format (claims table, decoded SD-JWT payload +
  disclosures, or decoded mDoc claims + signature status), plus the raw
  credential behind a toggle.

## Run it

Certify has to already be running (`../docker-compose/`).

```bash
cd ..                          # into certify/
python3 -m venv .venv          # first time only
source .venv/bin/activate
pip install -r scripts/requirements.txt -r demo-ui/requirements.txt
cd demo-ui
python3 server.py
```

Open http://localhost:5001.

## How it's built

`server.py` is a small Flask app:

| Route | What it does |
|---|---|
| `GET /` | serves `index.html` |
| `GET /healthz` | liveness check |
| `POST /api/issue` | runs `../scripts/issuance_flow.py` for the requested format, returns steps + credential as JSON |
| `GET /api/identity` | reads the current identity fields from the CSV |
| `POST /api/identity` | writes new field values, restarts Certify, waits for it to be healthy, then responds |

`index.html` is plain HTML/CSS/JS, no build step, no framework — it calls
those endpoints and renders what comes back. Format-specific rendering
(claims table vs. decoded SD-JWT vs. decoded mDoc) lives entirely in
`renderResult()` in the page's own script.

The page is meant to look decent, but the server underneath it isn't trying
to be a toy: `/healthz` for a liveness check, JSON error responses instead of
Flask's default HTML error page, and the debugger is off unless you
explicitly set `DEMO_UI_DEBUG=1` (it can execute arbitrary code if it's ever
reachable from outside your machine, so it shouldn't be on by default). The
actual issuance logic lives in `../scripts/issuance_flow.py`, shared with the
CLI test script — this file is just the HTTP wrapper around it, plus the
identity-editing endpoints in `../scripts/identity_store.py` and
`../scripts/certify_control.py`.

## Why saving identity data takes about a minute

`POST /api/identity` restarts the `certify` Docker container and waits for
it to report healthy again before responding — genuinely a 1-2 minute
round trip, which is why the UI shows a "restarting" banner instead of just
sitting there. This isn't a slow implementation choice; it's a real
constraint of the bundled `MockCSVDataProviderPlugin`, which loads the
identity CSV once at container startup and does not re-read it per request.
Confirmed by testing directly — editing the file alone didn't change the
next issued credential, only a restart did.
