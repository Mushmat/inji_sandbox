# Issuer Demo UI

A toy page to show the issuer piece working without reading terminal output.
Not the team's playground UI — that's a separate, bigger piece someone else
owns. This is just for showing teammates (and eventually the pitch/demo
video) that the issuer side is real and working.

Click a button, it runs the actual OpenID4VCI flow against the local Certify
instance and MOSIP Collab's mock eSignet, and shows each step plus the
credential that comes back.

## Run it

Certify has to already be running (`../docker-compose/`).

```bash
pip install -r requirements.txt
python3 server.py
```

Open http://localhost:5001, click either button.

## How it's built

`server.py` is a small Flask app: one route serves `index.html`, one route
(`POST /api/issue`) runs the flow from `../scripts/issuance_flow.py` and
returns the steps and the final credential as JSON. `index.html` is plain
HTML/CSS/JS, no build step, no framework — it just calls that one endpoint
and renders what comes back.

The page is a toy, but the server underneath it isn't trying to be one:
`GET /healthz` for a liveness check, JSON error responses instead of Flask's
default HTML error page, and Flask's debugger is off unless you explicitly
set `DEMO_UI_DEBUG=1` (it can execute arbitrary code if it's ever reachable
from outside your machine, so it shouldn't be on by default). The actual
issuance logic lives in `issuance_flow.py`, not here — this file is just the
HTTP wrapper around it.
