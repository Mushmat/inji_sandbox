"""Runs one issue -> hold -> present -> verify cycle for a chosen issuer, wallet and verifier.

The protocol work is done by the existing, tested modules: certify/scripts/issuance_flow.py
(through the Playground wallet) and verify/scripts/presentation_flow.py. This module only
sequences them, labels every step with its phase and its sender/receiver, and records the result.
"""

import json
import logging
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import quote

import requests

import catalog
import identity
import store
from config import CERTIFY_PUBLIC_ISSUER, CERTIFY_URL, INJI_WEB_URL, ROOT, VERSIONS

import presentation_flow  # verify/scripts
from steps import StepLog
from wallet import PRESENTABLE, HolderWallet

logger = logging.getLogger(__name__)

CONFIG_IDS = {"ldp_vc": "FarmerCredential", "vc+sd-jwt": "FarmerCredentialSdJwt", "mso_mdoc": "MobileDrivingLicense"}
PHONE_TIMEOUT_S = 6 * 60

_wallet = HolderWallet()
_wallet_lock = threading.Lock()  # the Playground wallet is shared state
_registry_lock = threading.Lock()
_active: dict = {}


class RunBusy(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _target(url: str):
    if not url:
        return None
    if "esignet" in url:
        return "auth_server"
    if "/certify" in url or ":8090" in url:
        return "issuer"
    if "/verify" in url or "trycloudflare" in url:
        return "verifier"
    return None


def _presentation_phase(name: str) -> str:
    n = name.lower()
    if "holds the credential" in n:
        return "hold"
    if "test issuer signs" in n or "attacker makes" in n:
        return "issue"
    if any(k in n for k in ("waits", "fetches", "runs its own checks", "result", "answered")):
        return "verify"
    return "present"


class Run:
    """One run. `segments` hold the raw step lists as the flows fill them in, so a
    poll mid-run already shows the steps taken so far."""

    def __init__(self, issuer, wallet, verifier, fmt, scenario, compat):
        self.doc = {
            "id": uuid.uuid4().hex[:12], "created_at": _now(), "finished_at": None, "duration_ms": None,
            "status": "running", "phase": "issue", "issuer": issuer, "wallet": wallet, "verifier": verifier,
            "format": fmt, "scenario": scenario, "versions": VERSIONS, "compat": compat,
            "credential": None, "proof_type": None, "outcome": None, "verifier_result": None,
            "playground_checks": [], "suspected_gaps": [], "unsupported": None, "awaiting": None, "error": None,
        }
        self.segments = []
        self._t0 = time.monotonic()

    def segment(self, kind: str, steps: list = None) -> list:
        steps = steps if steps is not None else []
        self.segments.append((kind, steps))
        return steps

    def local(self, phase, sender, receiver, name, detail, ok=True, note=None):
        entry = {"name": name, "method": "LOCAL", "url": None, "status": None, "ok": ok, "response": detail,
                 "phase": phase, "from": sender, "to": receiver}
        if note:
            entry["note"] = note
        self.segment("local", [entry])

    def steps(self) -> list:
        out = []
        for kind, raw in self.segments:
            for s in list(raw):
                step = dict(s)
                if kind == "issuance":
                    step.setdefault("phase", "issue")
                    step["from"], step["to"] = "wallet", _target(step.get("url"))
                elif kind == "presentation":
                    step["phase"] = _presentation_phase(step.get("name", ""))
                    actor = step.get("actor")
                    if step.get("method") == "LOCAL":
                        step["from"] = step["to"] = {"verifier": "relying_party"}.get(actor, actor)
                    elif actor == "verifier":
                        step["from"], step["to"] = "relying_party", "verifier"
                    else:
                        step["from"], step["to"] = actor, _target(step.get("url"))
                step["seq"] = len(out) + 1
                out.append(step)
        return out

    def view(self) -> dict:
        return {**self.doc, "steps": self.steps()}

    def finish(self, status="done"):
        self.doc["status"] = status
        self.doc["phase"] = "done"
        self.doc["awaiting"] = None
        self.doc["finished_at"] = _now()
        self.doc["duration_ms"] = int((time.monotonic() - self._t0) * 1000)


# ------------------------------------------------------------------ public API

def start(issuer, wallet, verifier, fmt, scenario) -> dict:
    compat = catalog.check(issuer, wallet, verifier, fmt, scenario)
    if not compat["runnable"]:
        raise ValueError(" ".join(compat["blockers"]))
    if (issuer == "certify" or wallet == "inji_web") and identity.certify_restarting():
        raise RunBusy("Certify is restarting to load the new credential details. Try again when it's back.")
    with _registry_lock:
        busy = [r for r in _active.values() if r.doc["status"] in ("running", "waiting")]
        if busy:
            raise RunBusy(f"Run {busy[0].doc['id']} is still in progress. Wait for it or cancel it first.")
        run = Run(issuer, wallet, verifier, fmt, scenario, compat)
        _active[run.doc["id"]] = run
    store.save(run.view())
    target = _interactive_issue if catalog.WALLETS[wallet]["interactive"] else _automatic
    threading.Thread(target=_guard, args=(run, target), daemon=True).start()
    return run.view()


def get(run_id: str):
    run = _active.get(run_id)
    return run.view() if run else store.get(run_id)


def resume(run_id: str) -> dict:
    """The person has the card in Inji Web: move on to the presentation."""
    run = _active.get(run_id)
    if not run or run.doc["status"] != "waiting" or (run.doc["awaiting"] or {}).get("kind") != "inji_web_issue":
        raise ValueError("This run isn't waiting for an Inji Web download.")
    run.doc["status"] = "running"
    run.doc["awaiting"] = None
    threading.Thread(target=_guard, args=(run, _interactive_present), daemon=True).start()
    return run.view()


def cancel(run_id: str) -> dict:
    run = _active.get(run_id)
    if not run or run.doc["status"] not in ("running", "waiting"):
        raise ValueError("Only a run in progress can be cancelled.")
    run.doc["error"] = "Cancelled."
    run.finish("cancelled")
    store.save(run.view())
    return run.view()


def wallet_summary() -> dict:
    return _wallet.summary()


# ------------------------------------------------------------------ flows

def _guard(run: Run, fn):
    try:
        fn(run)
    except Exception as e:  # a run must always end in a stored state, never hang as "running"
        logger.exception("run %s failed", run.doc["id"])
        run.doc["error"] = f"{type(e).__name__}: {e}"
        run.finish("error")
    if run.doc["status"] in ("done", "error", "cancelled"):
        store.save(run.view())


def _automatic(run: Run):
    fmt = run.doc["format"]
    with _wallet_lock:
        if not _issue_to_playground_wallet(run):
            return
        if _cancelled(run):
            return
        run.doc["phase"] = "present"
        reason = _presentation_blocker(run)
        if reason:
            _record_unsupported(run, reason)
            return
        with _live_steps(run):
            result = presentation_flow.run_presentation(fmt, run.doc["scenario"], source="wallet", wallet=_wallet)
    if _cancelled(run):
        return
    _apply_result(run, result)


def _issue_to_playground_wallet(run: Run) -> bool:
    fmt, issuer = run.doc["format"], run.doc["issuer"]
    if issuer == "test_issuer":
        result = _wallet.receive_from_test_issuer(fmt, subject=identity.subject())
        cred = result["credential"]
        run.local("issue", "issuer", "wallet", "Test issuer signs the credential and hands it to the wallet",
                  {"issuer": "did:key test issuer (not Inji)", "format": fmt, "credential": cred},
                  note="No OpenID4VCI here: the test issuer exists to show a verifier handling a stranger's credential.")
    else:
        _offer_and_metadata(run, fmt)
        result = _wallet.receive_from_certify(fmt)
        run.segment("issuance", result.get("steps", []))
        if not result.get("ok"):
            run.doc["error"] = f"Issuance failed: {result.get('error')}"
            run.finish("error")
            return False
        cred = result["credential"]

    run.doc["phase"] = "hold"
    run.doc["credential"], run.doc["proof_type"] = _describe(fmt, cred, result.get("credential_decoded"))
    held = {"format": fmt, **run.doc["credential"],
            "stored": fmt in PRESENTABLE,
            "holder": _wallet.did}
    run.local("hold", "wallet", "wallet", "Wallet stores the credential", held,
              note="Bound to the wallet's own EC P-256 key, so it can prove possession later.")
    return True


def _offer_and_metadata(run: Run, fmt: str):
    offer = {
        "credential_issuer": CERTIFY_PUBLIC_ISSUER,
        "credential_configuration_ids": [CONFIG_IDS[fmt]],
        "grants": {"authorization_code": {"issuer_state": uuid.uuid4().hex}},
    }
    run.local("issue", "issuer", "wallet", "Issuer offers the credential",
              {"credential_offer": offer,
               "credential_offer_uri": "openid-credential-offer://?credential_offer=" + quote(json.dumps(offer))},
              note="Issuer-initiated offer (OpenID4VCI draft 13, section 4.1) for Certify's "
                   f"{CONFIG_IDS[fmt]} configuration, written by the Playground from Certify's metadata. "
                   "Certify 0.14 can also mint offers itself (pre-authorized code), which needs its own "
                   "authorization server switched on; this setup logs in through Collab's eSignet instead.")
    url = f"{CERTIFY_URL}/.well-known/openid-credential-issuer"
    try:
        r = requests.get(url, timeout=10)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:2000]
        run.segment("issuance", [{"name": "Wallet reads the issuer metadata", "method": "GET", "url": url,
                                  "status": r.status_code, "ok": r.ok, "response": body}])
    except requests.RequestException as e:
        run.segment("issuance", [{"name": "Wallet reads the issuer metadata", "method": "GET", "url": url,
                                  "status": None, "ok": False, "response": str(e)}])


def _presentation_blocker(run: Run):
    fmt = run.doc["format"]
    w, v = catalog.WALLETS[run.doc["wallet"]], catalog.VERIFIERS[run.doc["verifier"]]
    if fmt not in w["present"]:
        return next((l for l in run.doc["compat"]["limits"] if "present" in l), f"{w['name']} can't present {fmt}.")
    if fmt not in v["formats"]:
        return presentation_flow.MDOC_REASON if fmt == "mso_mdoc" else f"{v['name']} can't receive {fmt}."
    return None


def _record_unsupported(run: Run, reason: str):
    run.local("present", "playground", "playground", "Presentation not attempted", {"reason": reason}, ok=False)
    run.doc["unsupported"] = reason
    run.doc["outcome"] = {"expected": catalog.SCENARIOS[run.doc["scenario"]]["expected"], "result": "UNSUPPORTED",
                          "verdict": "UNSUPPORTED", "explanation": reason}
    run.finish()


def _apply_result(run: Run, result: dict):
    for key in ("verifier_result", "playground_checks", "suspected_gaps", "outcome", "session", "presentation"):
        if key in result:
            run.doc[key] = result[key]
    if not run.doc["proof_type"]:
        # Inji Web runs: the Playground never holds the credential, so read it from what Inji Verify returned
        creds = (run.doc.get("verifier_result") or {}).get("credentials") or []
        if creds and creds[0]:
            _, run.doc["proof_type"] = _describe(run.doc["format"], creds[0], None)
    if not result.get("ok"):
        run.doc["error"] = result.get("error")
        run.doc["outcome"] = run.doc.get("outcome") or {
            "expected": catalog.SCENARIOS[run.doc["scenario"]]["expected"], "result": "ERROR", "verdict": "ERROR",
            "explanation": result.get("error")}
    run.finish("done" if result.get("ok") else "error")


@contextmanager
def _live_steps(run: Run):
    """run_presentation() makes its own StepLog. Handing it one whose list is already
    registered on the run lets the UI show each step as it happens."""
    original = presentation_flow.StepLog

    def factory():
        log = original()
        run.segment("presentation", log.steps)
        return log

    presentation_flow.StepLog = factory
    try:
        yield
    finally:
        presentation_flow.StepLog = original


def _cancelled(run: Run) -> bool:
    return run.doc["status"] == "cancelled"


# ------------------------------------------------------------------ Inji Web (a person drives the wallet)

def _interactive_issue(run: Run):
    fmt = run.doc["format"]
    entry = _mimoto_issuer_entry()
    run.local("issue", "issuer", "wallet", "Inji Web lists our Certify as an issuer",
              {"mimoto_issuers_config": entry, "credential_configuration_id": CONFIG_IDS[fmt]},
              note="Mimoto reads this entry, fetches Certify's metadata and runs the OpenID4VCI flow when you "
                   "download the card. That traffic stays inside Mimoto, so the Playground can't show it.")
    run.doc["status"] = "waiting"
    run.doc["awaiting"] = {
        "kind": "inji_web_issue",
        "title": "Download the card in Inji Web",
        "link": INJI_WEB_URL,
        "instructions": [
            "Open Inji Web and sign in with Google.",
            "Choose Farmer Issuer (Local Certify), then "
            + ("Farmer Verifiable Credential." if fmt == "ldp_vc" else "the SD-JWT Farmer credential."),
            "Log in with individual ID 2154189532 and OTP 111111.",
            "When the card shows in your wallet, come back and continue.",
        ],
    }


def _interactive_present(run: Run):
    fmt, scenario = run.doc["format"], run.doc["scenario"]
    run.doc["phase"] = "hold"
    run.local("hold", "wallet", "wallet", "Holder confirms the card is in Inji Web", {"format": fmt}, ok=True)
    run.doc["phase"] = "present"
    started = presentation_flow.start_phone_session(fmt, scenario)
    seg = run.segment("presentation", list(started.get("steps", [])))
    if not started.get("ok"):
        run.doc["error"] = started.get("error")
        run.finish("error")
        return
    run.doc["status"] = "waiting"
    run.doc["awaiting"] = {
        "kind": "inji_web_present",
        "title": "Approve the presentation in Inji Web",
        "link": started["inji_web_link"],
        "instructions": ["Open the request in Inji Web.", "Pick the Farmer card and consent to share it.",
                         "This page picks up Inji Verify's result by itself."],
        "qr": started.get("qr"),
        "request_uri": started.get("authorization_request_uri"),
    }
    deadline = time.monotonic() + PHONE_TIMEOUT_S
    while time.monotonic() < deadline and not _cancelled(run):
        polled = presentation_flow.poll_phone_session(started["id"])
        seg[:] = polled.get("steps", seg)
        if polled.get("done") or not polled.get("ok", True):
            run.doc["status"] = "running"
            run.doc["phase"] = "verify"
            _apply_result(run, polled)
            return
        time.sleep(2)
    if not _cancelled(run):
        run.doc["error"] = "No answer from the wallet within six minutes."
        run.finish("error")


def _mimoto_issuer_entry() -> dict:
    path = ROOT / "wallet" / "docker-compose" / "config" / "mimoto-issuers-config.json"
    try:
        issuers = json.loads(path.read_text(encoding="utf-8-sig"))["issuers"]
        return next(i for i in issuers if i.get("issuer_id") == "FarmerIssuer")
    except (OSError, ValueError, StopIteration):
        return {"issuer_id": "FarmerIssuer", "note": "wallet/docker-compose/config/mimoto-issuers-config.json not readable"}


# ------------------------------------------------------------------ credential description

def _describe(fmt: str, cred, decoded):
    """(summary for the UI, proof type for the report)."""
    if fmt == "ldp_vc" and isinstance(cred, dict):
        proof = cred.get("proof") or {}
        issuer = cred.get("issuer")
        subject = {k: v for k, v in (cred.get("credentialSubject") or {}).items() if k != "face"}
        return ({"issuer": issuer if isinstance(issuer, str) else (issuer or {}).get("id"),
                 "types": cred.get("type"), "issued": cred.get("issuanceDate"), "expires": cred.get("expirationDate"),
                 "verification_method": proof.get("verificationMethod"), "claims": subject},
                proof.get("type"))
    if fmt == "vc+sd-jwt" and isinstance(cred, str):
        import sdjwt  # verify/scripts
        parsed = sdjwt.parse(cred)
        view, _, _ = sdjwt.reconstruct(parsed["payload"], parsed["disclosures"])
        header = parsed.get("header") or {}
        claims = {k: v for k, v in (view.get("credentialSubject") or view).items()
                  if k not in ("face", "_sd", "_sd_alg", "cnf")}
        return ({"issuer": view.get("iss"), "vct": view.get("vct"), "claims": claims,
                 "disclosable": [d["name"] for d in parsed["disclosures"]], "header": header},
                f"SD-JWT ({header.get('alg', '?')})")
    if fmt == "mso_mdoc":
        d = decoded or {}
        return ({"doctype": d.get("docType"), "claims": d.get("claims"), "signed": d.get("signed")},
                "COSE_Sign1 (mso_mdoc)")
    return ({"raw": cred}, None)
