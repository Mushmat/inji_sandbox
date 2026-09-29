"""
A stand-in for Inji Verify's verify-service 0.18.2, for offline tests only.

It copies the HTTP contract (paths, field names, status codes, error codes)
and the behaviour we read in the v0.18.2 source, including the parts that
look like gaps, so the offline tests exercise the same decisions:

  - submission: vp_token + presentation_submission required; for JSON-LD
    presentations proof.challenge must equal the nonce and proof.domain the
    clientId, else 400 NONCE_VALIDATION_FAILED / CLIENT_ID_VALIDATION_FAILED
    (VerifiablePresentationSubmissionServiceImpl.submit)
  - SD-JWT: issuer signature, disclosure digests and KB-JWT signature/sd_hash
    are checked, but the KB-JWT nonce/aud are not compared with the session (F3)
  - presentation_definition constraints are not evaluated (F2)
  - the stored presentation_definition keeps only the DTO fields (F4)

It is a model, not the real thing: the live test (test_presentation_live.py)
is what confirms behaviour against the real container.
"""
import hashlib
import json
import os
import sys
import threading
import time
import uuid

from flask import Flask, jsonify, request
import logging

from werkzeug.serving import make_server

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import sdjwt  # noqa: E402
from checks import x5c_public_key  # noqa: E402
from did_resolver import jwk_of_did, jwk_to_public_key, resolve_key  # noqa: E402
from jsonld_proofs import b64url, verify_ed25519_2020, verify_jws2020  # noqa: E402


def _dto_pd(pd):
    """Keep what VPDefinitionResponseDto / InputDescriptorDto / FieldDTO / FilterDTO keep."""
    def field(f):
        out = {"path": f.get("path")}
        if f.get("filter"):
            out["filter"] = {k: f["filter"][k] for k in ("type", "pattern") if k in f["filter"]}
        return out
    return {
        "id": pd.get("id"), "name": pd.get("name"), "purpose": pd.get("purpose"), "format": pd.get("format"),
        "input_descriptors": [{"id": d.get("id"), "name": d.get("name"), "purpose": d.get("purpose"), "format": d.get("format"),
                               "constraints": {"fields": [field(f) for f in (d.get("constraints") or {}).get("fields", [])]}}
                              for d in pd.get("input_descriptors", [])],
    }


class FakeInjiVerify:
    def __init__(self):
        self.app = Flask("fake-inji-verify")
        self.requests, self.submissions = {}, {}
        self.base = None
        a = self.app

        @a.post("/v1/verify/vp-request")
        def create():
            b = request.get_json()
            rid, txn = "req_" + uuid.uuid4().hex[:12], "txn_" + uuid.uuid4().hex[:12]
            details = {"responseType": "vp_token", "responseMode": "direct_post", "clientId": b["clientId"],
                       "presentationDefinition": _dto_pd(b["presentationDefinition"]),
                       "nonce": b.get("nonce") or uuid.uuid4().hex, "responseUri": f"{self.base}/vp-submission/direct-post",
                       "acceptVPWithoutHolderProof": False, "responseCodeValidationRequired": False}
            self.requests[rid] = {"txn": txn, "details": details, "expires": int(time.time() * 1000) + 300000}
            return jsonify({"transactionId": txn, "requestId": rid, "authorizationDetails": details,
                            "expiresAt": self.requests[rid]["expires"]}), 201

        # Stands in for Certify's /.well-known/did.json in the forged-issuer test.
        self.certify_did_document = {"id": "did:web:mushmat.github.io:inji-did", "verificationMethod": []}

        @a.get("/certify/did.json")
        def certify_did():
            return jsonify(self.certify_did_document)

        @a.get("/v1/verify/vp-request/<rid>/status")
        def status(rid):
            if rid not in self.requests:
                return jsonify({"errorCode": "INVALID_REQUEST_ID"}), 404
            return jsonify({"status": "VP_SUBMITTED" if rid in self.submissions else "ACTIVE"})

        @a.post("/v1/verify/vp-submission/direct-post")
        def direct_post():
            vp_token, ps, state = request.form.get("vp_token"), request.form.get("presentation_submission"), request.form.get("state")
            if not (vp_token and ps):
                return "Invalid response: either vp_token and presentation_submission must be provided, or error must be provided.", 400
            req = self.requests.get(state)
            if req is None:
                return "", 404
            d = req["details"]
            if vp_token.lstrip().startswith("{"):
                proof = json.loads(vp_token).get("proof") or {}
                if not proof.get("challenge") or not proof.get("domain"):
                    return jsonify({"errorCode": "CLIENT_ID_NONCE_VALIDATION_FAILED"}), 400
                if proof["challenge"] != d["nonce"]:
                    return jsonify({"errorCode": "NONCE_VALIDATION_FAILED"}), 400
                if proof["domain"] != d["clientId"]:
                    return jsonify({"errorCode": "CLIENT_ID_VALIDATION_FAILED"}), 400
            self.submissions[state] = {"vp_token": vp_token, "presentation_submission": json.loads(ps)}
            return jsonify({}), 200

        @a.post("/v1/verify/v2/vp-results/<txn>")
        def results(txn):
            rid = next((r for r, v in self.requests.items() if v["txn"] == txn and r in self.submissions), None)
            if rid is None:
                return jsonify({"errorCode": "INVALID_TRANSACTION_ID"}), 404
            token = self.submissions[rid]["vp_token"]
            try:
                creds = [self._ldp(json.loads(token))] if token.lstrip().startswith("{") else [self._sd(token)]
            except ValueError:
                return jsonify({"errorCode": "VP_VERIFICATION_FAILED",
                                "errorMessage": "VP verification failed due to runtime exception during VP verification"}), 500
            creds = [c for group in creds for c in (group if isinstance(group, list) else [group])]
            return jsonify({"transactionId": txn, "allChecksSuccessful": all(c["allChecksSuccessful"] for c in creds),
                            "credentialResults": creds})

    @staticmethod
    def _result(vc, holder_ok, sig_ok, exp_ok, claims):
        return {"verifiableCredential": vc if isinstance(vc, str) else json.dumps(vc),
                "holderProofCheck": {"valid": holder_ok, "error": None if holder_ok else {"errorCode": "ERR_INVALID_HOLDER_PROOF"}},
                "schemaAndSignatureCheck": {"valid": sig_ok, "error": None if sig_ok else {"errorCode": "ERR_SIGNATURE_VERIFICATION_FAILED"}},
                "expiryCheck": {"valid": exp_ok} if sig_ok else None, "statusCheck": [],
                "claims": claims if sig_ok else {}, "allChecksSuccessful": holder_ok and sig_ok and exp_ok}

    def _ldp(self, vp):
        vm = vp["proof"]["verificationMethod"]
        if "=" in vm.split("#")[0]:
            # vc-verifier DidPublicKeyResolver.DID_MATCHER has no "=" in method-specific ids (F9)
            raise ValueError("Given did url is not supported")
        key, _ = resolve_key(vm)
        holder_ok = verify_jws2020(vp, key)
        out = []
        for vc in vp["verifiableCredential"]:
            ikey, _ = resolve_key(vc["proof"]["verificationMethod"])
            sig_ok = verify_ed25519_2020(vc, ikey)
            exp_ok = vc.get("expirationDate", "9999") > time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            out.append(self._result(vc, holder_ok, sig_ok, exp_ok, vc.get("credentialSubject", {})))
        return out

    def _sd(self, token):
        p = sdjwt.parse(token)
        view, unmatched, _ = sdjwt.reconstruct(p["payload"], p["disclosures"])
        x5c = p["header"].get("x5c")
        if not x5c:
            # vc-verifier SdJwtVerifier: the key comes only from x5c
            r = self._result(token, False, False, False, {})
            r["schemaAndSignatureCheck"]["error"] = {"errorCode": "ERR_SIGNATURE_VERIFICATION_FAILED",
                                                     "errorMessage": "Exception during Verification: getX509CertChain(...) must not be null"}
            r["holderProofCheck"] = None
            return r
        # ...with no check that the certificate belongs to iss or chains to anything trusted (F10)
        key = x5c_public_key(x5c[0])
        sig_ok = sdjwt.verify_jws(p["jwt"], key) and not unmatched
        holder_ok = False
        if p["kb_jwt"]:
            kbp = sdjwt.decode_jwt_part(p["kb_jwt"].split(".")[1])
            hk = jwk_to_public_key(jwk_of_did(p["payload"]["cnf"]["kid"]))
            sd_hash = b64url(hashlib.sha256(p["presented_part"].encode()).digest())
            # nonce and aud deliberately not compared with the session (F3)
            holder_ok = sdjwt.verify_jws(p["kb_jwt"], hk) and kbp.get("sd_hash") == sd_hash
        sig_ok = sig_ok and holder_ok  # Inji reports KB errors through schemaAndSignatureCheck
        exp_ok = p["payload"].get("exp", 1e12) > time.time()
        return self._result(token, holder_ok, sig_ok, exp_ok, view.get("credentialSubject", {}))

    # ----------------------------------------------------------- lifecycle
    def __enter__(self):
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        self.server = make_server("127.0.0.1", 0, self.app, threaded=True)
        self.base = f"http://127.0.0.1:{self.server.server_port}/v1/verify"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
