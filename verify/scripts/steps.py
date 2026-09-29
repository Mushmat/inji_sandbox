"""
Step recorder shared by the wallet, the verifier client and the flow.

Each entry has the same keys as Chirayu's issuance steps (name, method, url,
status, ok, response) so both demo UIs can render them the same way, plus:
  actor    - who made the call: "verifier" (the relying-party backend),
             "wallet", or "playground" (our own independent checks)
  request  - what was sent
  note     - one plain-language line on why this step exists
Local steps (no HTTP) use method "LOCAL" and status None.
"""
import json


def _body(resp):
    try:
        return resp.json()
    except ValueError:
        text = resp.text or ""
        return text[:2000]


class StepLog:
    def __init__(self):
        self.steps = []

    def http(self, name, actor, method, url, resp, request=None, note=None, ok=None):
        entry = {
            "name": name,
            "actor": actor,
            "method": method,
            "url": url,
            "status": resp.status_code,
            "ok": (200 <= resp.status_code < 300) if ok is None else ok,
            "request": request,
            "response": _body(resp),
        }
        if note:
            entry["note"] = note
        self.steps.append(entry)
        return entry

    def local(self, name, actor, detail, ok=True, note=None):
        entry = {"name": name, "actor": actor, "method": "LOCAL", "url": None, "status": None, "ok": ok, "response": detail}
        if note:
            entry["note"] = note
        self.steps.append(entry)
        return entry

    def error(self, name, actor, method, url, exc, request=None):
        entry = {"name": name, "actor": actor, "method": method, "url": url, "status": None, "ok": False,
                 "request": request, "response": f"{type(exc).__name__}: {exc}"}
        self.steps.append(entry)
        return entry


def short(value, limit=120):
    s = value if isinstance(value, str) else json.dumps(value)
    return s if len(s) <= limit else s[: limit - 3] + "..."
