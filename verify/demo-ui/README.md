# verify/demo-ui

A browser view of the Present & Verify flow, styled like `certify/demo-ui` so the two sit side by side.
It is a thin wrapper around `../scripts/presentation_flow.py`: everything it shows comes from that flow.

```bash
pip install -r requirements.txt
python3 server.py          # http://localhost:5002  (PORT to change)
```

Needs Inji Verify (`../docker-compose`) and, to receive real credentials, Certify
(`../../certify/docker-compose`) with the holder-key patch applied. The *Services* box says which of
these is missing.

1. **Holder wallet** (left): *Receive from Certify* runs Chirayu's issuance flow with the wallet's key
   and stores the credential. *Use offline test issuer* is the fallback when Certify isn't available.
2. **What to present**: pick JSON-LD or SD-JWT and a scenario. mDoc is shown disabled with the reason.
3. **Present with built-in wallet** runs the whole exchange. **Present with a phone wallet (QR)**
   shows the request as a QR code and waits for a wallet app to answer.
4. **Protocol steps**: each call, tagged by who made it (verifier / wallet / issuer / playground). Click
   one for its URL, request and response.
5. **Result**: what it should be, what Inji Verify said, PASS/FAIL, both sets of checks, and a red box
   for a suspected gap.

`DEMO_UI_DEBUG=1` turns on Flask's debugger. Keep it off otherwise: the debugger can run arbitrary code
if the server is reachable from other machines.
