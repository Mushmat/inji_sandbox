#!/usr/bin/env python3
"""
Demo server for the verifier piece (FR4, Present & Verify). Same idea as
certify/demo-ui: a thin HTTP wrapper around the real, tested flow in
../scripts/presentation_flow.py, so the steps can be watched in a browser.

Usage:
    pip install -r requirements.txt
    python3 server.py
    open http://localhost:5002

Set DEMO_UI_DEBUG=1 for Flask's debugger and auto-reload while working on
this file. Leave it off otherwise: the debugger can execute arbitrary code if
it's ever reachable from outside your machine.
"""
import logging
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import requests  # noqa: E402
from flask import Flask, jsonify, request, send_from_directory  # noqa: E402

from presentation_flow import (MDOC_REASON, SCENARIOS, poll_phone_session, run_presentation,  # noqa: E402
                               start_phone_session)
from verifier_client import VerifierClient  # noqa: E402
from wallet import PRESENTABLE, HolderWallet, WalletError, load_run_issuance  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
CERTIFY_WELL_KNOWN = os.environ.get("CERTIFY_WELL_KNOWN", "http://localhost:8090/v1/certify/.well-known/openid-credential-issuer")

app = Flask(__name__, static_folder=None)
wallet = HolderWallet()
wallet_lock = threading.Lock()  # one flow at a time: they share the wallet


@app.route("/")
def index():
    return send_from_directory(HERE, "index.html")


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.route("/api/status")
def status():
    try:
        certify_ok = requests.get(CERTIFY_WELL_KNOWN, timeout=3).status_code == 200
    except requests.RequestException:
        certify_ok = False
    try:
        load_run_issuance()
        patch = {"ok": True, "detail": "issuance_flow.py accepts holder_key"}
    except WalletError as e:
        patch = {"ok": False, "detail": str(e)}
    return jsonify({"verifier": VerifierClient().health(), "certify": {"ok": certify_ok, "url": CERTIFY_WELL_KNOWN},
                    "patch": patch, "scenarios": SCENARIOS, "mdoc_reason": MDOC_REASON})


@app.route("/api/wallet")
def get_wallet():
    return jsonify(wallet.summary())


@app.route("/api/wallet/receive", methods=["POST"])
def receive():
    body = request.get_json(silent=True) or {}
    fmt, source = body.get("format", "ldp_vc"), body.get("source", "certify")
    if fmt not in PRESENTABLE:
        return jsonify({"ok": False, "error": f"format must be one of {list(PRESENTABLE)}"}), 400
    with wallet_lock:
        try:
            result = wallet.receive_from_test_issuer(fmt) if source == "test" else wallet.receive_from_certify(fmt)
        except Exception:
            logger.exception("unexpected error receiving a credential")
            return jsonify({"ok": False, "error": "internal error, check server logs"}), 500
    result = {k: v for k, v in result.items() if k in ("ok", "error", "steps", "format", "wallet")}
    result["wallet_summary"] = wallet.summary()
    return jsonify(result), (200 if result["ok"] else 502)


@app.route("/api/wallet/clear", methods=["POST"])
def clear():
    with wallet_lock:
        wallet.clear()
    return jsonify(wallet.summary())


@app.route("/api/present", methods=["POST"])
def present():
    body = request.get_json(silent=True) or {}
    with wallet_lock:
        try:
            result = run_presentation(body.get("format", "ldp_vc"), body.get("scenario", "none"), source="wallet", wallet=wallet)
        except Exception:
            logger.exception("unexpected error running the presentation flow")
            return jsonify({"ok": False, "error": "internal error, check server logs"}), 500
    return jsonify(result), (200 if result["ok"] else 502)


@app.route("/api/present/phone", methods=["POST"])
def phone_start():
    body = request.get_json(silent=True) or {}
    result = start_phone_session(body.get("format", "ldp_vc"), body.get("scenario", "none"))
    return jsonify(result), (200 if result["ok"] else 502)


@app.route("/api/present/phone/<sid>")
def phone_poll(sid):
    try:
        return jsonify(poll_phone_session(sid))
    except Exception:
        logger.exception("unexpected error polling a phone session")
        return jsonify({"ok": False, "error": "internal error, check server logs"}), 500


if __name__ == "__main__":
    debug = os.environ.get("DEMO_UI_DEBUG") == "1"
    app.run(port=int(os.environ.get("PORT", "5002")), debug=debug, threaded=True)
