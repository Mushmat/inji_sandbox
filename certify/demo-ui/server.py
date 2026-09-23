#!/usr/bin/env python3
"""
Toy demo server for the issuer piece - not the team's playground UI (that's
being built separately). This is just here to show the issuance flow
working, step by step, without needing Postman or reading terminal output.

The UI is deliberately simple. The backend underneath it (issuance_flow.py)
is the real, tested issuer pipeline - this file is just a thin HTTP wrapper
around it.

Usage:
    pip install -r requirements.txt
    python3 server.py
    open http://localhost:5001

Set DEMO_UI_DEBUG=1 to run with Flask's debugger and auto-reload while
working on this file. Leave it off otherwise - the debugger can execute
arbitrary code if it's ever reachable from outside your machine.
"""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from flask import Flask, jsonify, request, send_from_directory
from issuance_flow import run_issuance, VALID_FORMATS
from identity_store import read_identity, update_identity, EDITABLE_FIELDS
from certify_control import start_restart, get_status

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder=".", static_url_path="")


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.route("/api/issue", methods=["POST"])
def issue():
    body = request.get_json(silent=True) or {}
    vc_format = body.get("format", "ldp_vc")

    if vc_format not in VALID_FORMATS:
        return jsonify({"ok": False, "error": f"format must be one of {VALID_FORMATS}"}), 400

    try:
        result = run_issuance(vc_format)
    except Exception:
        # run_issuance already catches network/response errors and returns a
        # clean result - this is only a safety net for anything it doesn't.
        logger.exception("unexpected error running issuance flow")
        return jsonify({"ok": False, "error": "internal error, check server logs"}), 500

    return jsonify(result), (200 if result["ok"] else 502)


@app.route("/api/identity", methods=["GET"])
def get_identity():
    try:
        return jsonify({"ok": True, "identity": read_identity(), "fields": EDITABLE_FIELDS})
    except (OSError, ValueError) as e:
        logger.exception("failed to read identity data")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/identity", methods=["POST"])
def save_identity():
    body = request.get_json(silent=True) or {}
    if not body:
        return jsonify({"ok": False, "error": "no fields provided"}), 400

    try:
        updated = update_identity(body)
    except (OSError, ValueError) as e:
        logger.exception("failed to write identity data")
        return jsonify({"ok": False, "error": str(e)}), 500

    # The CSV write above is what actually matters and it's already done -
    # that's never what's slow. Certify just caches the file at startup, so
    # the edit only takes effect once it restarts, and that restart runs in
    # the background rather than blocking this response: the client polls
    # /api/identity/status to watch it finish instead of one long request
    # that would eventually have to guess when "still going" becomes "call
    # it a failure."
    started = start_restart()
    return jsonify({
        "ok": True,
        "identity": updated,
        "restarting": True,
        "already_restarting": not started,
    })


@app.route("/api/identity/status", methods=["GET"])
def identity_restart_status():
    return jsonify(get_status())


if __name__ == "__main__":
    debug = os.environ.get("DEMO_UI_DEBUG") == "1"
    app.run(port=5001, debug=debug)
