#!/usr/bin/env python3
"""
Toy demo server for the issuer piece - not the team's playground UI (that's
being built separately). This is just here to show the issuance flow
working, step by step, without needing Postman or reading terminal output.

Usage:
    pip install -r requirements.txt
    python3 server.py
    open http://localhost:5001
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from flask import Flask, jsonify, request, send_from_directory
from issuance_flow import run_issuance

app = Flask(__name__, static_folder=".", static_url_path="")


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/api/issue", methods=["POST"])
def issue():
    vc_format = request.json.get("format", "ldp_vc")
    if vc_format not in ("ldp_vc", "vc+sd-jwt"):
        return jsonify({"ok": False, "error": "unknown format"}), 400
    result = run_issuance(vc_format)
    return jsonify(result)


if __name__ == "__main__":
    app.run(port=5001, debug=True)
