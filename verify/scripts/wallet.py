"""
The built-in holder wallet: keeps one holder key, receives credentials from
Chirayu's Certify flow (bound to that key), and answers OpenID4VP requests.

Why the wallet keeps its own key
--------------------------------
A presentation is signed by the holder, with the same key the credential was
bound to at issuance. Chirayu's run_issuance() originally generated a fresh
key per request and threw it away, so nothing could present the credential.
The patch in ../issuance_flow_holder_key.patch adds an optional holder_key
argument (fully backwards compatible); the wallet passes its key in.

Key choice: EC P-256 (ES256). Chirayu's FarmerCredential config accepts
RS256 and ES256 proof JWTs. RS256 would work for issuance, but Inji Verify
0.18.2 cannot check an RsaSignature2018 presentation proof (FINDINGS F8), so
the wallet signs JSON-LD presentations with JsonWebSignature2020 / ES256.

Files (git-ignored): verify/.wallet/holder_p256.pem and credentials.json.
"""
import copy
import inspect
import json
import os
import sys
import time
import uuid
from urllib.parse import parse_qs, urlparse

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

import pex
import sdjwt
from did_resolver import did_jwk, jwk_of_did, public_key_to_jwk, same_key
from jsonld_proofs import CREDENTIALS_V1, sign_jws2020

HERE = os.path.dirname(os.path.abspath(__file__))
VERIFY_DIR = os.path.dirname(HERE)
WALLET_DIR = os.environ.get("VERIFY_WALLET_DIR", os.path.join(VERIFY_DIR, ".wallet"))
CERTIFY_SCRIPTS_DIR = os.environ.get("CERTIFY_SCRIPTS_DIR", os.path.join(os.path.dirname(VERIFY_DIR), "certify", "scripts"))
REQUEST_TIMEOUT = 20

PRESENTABLE = ("ldp_vc", "vc+sd-jwt")
ALTERED_FARMER_ID = "000000000"


class WalletError(Exception):
    pass


class HolderWallet:
    def __init__(self, directory: str = None):
        self.dir = directory or WALLET_DIR
        os.makedirs(self.dir, exist_ok=True)
        self.key = self._load_or_create_key()
        self.public_jwk = public_key_to_jwk(self.key.public_key())
        self.did = did_jwk(self.key.public_key())
        self.credentials = self._load_credentials()

    # --------------------------------------------------------------- storage
    def _load_or_create_key(self):
        path = os.path.join(self.dir, "holder_p256.pem")
        if os.path.exists(path):
            with open(path, "rb") as f:
                return serialization.load_pem_private_key(f.read(), None)
        key = ec.generate_private_key(ec.SECP256R1())
        with open(path, "wb") as f:
            f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return key

    def _cred_path(self):
        return os.path.join(self.dir, "credentials.json")

    def _load_credentials(self):
        try:
            with open(self._cred_path()) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save(self):
        with open(self._cred_path(), "w") as f:
            json.dump(self.credentials, f, indent=2)

    def store(self, vc_format: str, credential, source: str):
        entry = {"format": vc_format, "credential": credential, "source": source,
                 "received_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        entry["bound_to_wallet_key"] = self.is_bound_to_me(vc_format, credential)
        self.credentials[vc_format] = entry
        self._save()
        return entry

    def clear(self):
        self.credentials = {}
        self._save()

    # --------------------------------------------------------------- binding
    def holder_id_in(self, vc_format: str, credential):
        """The holder DID the issuer wrote into the credential."""
        if vc_format == "ldp_vc":
            subject = credential.get("credentialSubject") or {}
            if isinstance(subject, list):
                subject = subject[0] if subject else {}
            return subject.get("id")
        if vc_format == "vc+sd-jwt":
            cnf = sdjwt.parse(credential)["payload"].get("cnf") or {}
            if "kid" in cnf:
                return cnf["kid"]
            if "jwk" in cnf:
                return "jwk:" + json.dumps(cnf["jwk"])
        return None

    def is_bound_to_me(self, vc_format: str, credential) -> bool:
        hid = self.holder_id_in(vc_format, credential)
        if not hid:
            return False
        if hid.startswith("jwk:"):
            return same_key(json.loads(hid[4:]), self.public_jwk)
        return same_key(jwk_of_did(hid), self.public_jwk)

    def holder_did_for(self, vc_format: str, credential) -> str:
        """Use the DID the issuer wrote (Certify builds did:jwk from the JWK in the
        proof header, including alg/use), so a verifier comparing it with
        credentialSubject.id sees the same key. Falls back to the wallet's own did:jwk.

        One adjustment: did:jwk must be base64url *without* padding (did:jwk spec,
        RFC 7515 base64url). Certify 0.14.0 writes it with "=" padding, and
        vc-verifier's DID parser rejects "=" ("Given did url is not supported"),
        so the presentation uses the unpadded form of the same DID (FINDINGS F9)."""
        hid = self.holder_id_in(vc_format, credential)
        if hid and hid.startswith("did:") and same_key(jwk_of_did(hid), self.public_jwk):
            return hid.rstrip("=") if hid.startswith("did:jwk:") else hid
        return self.did

    # ------------------------------------------------------------- receiving
    def receive_from_certify(self, vc_format: str) -> dict:
        """Runs Chirayu's issuance flow with this wallet's key. Returns his result
        dict (steps, ok, error, credential, ...). Never raises."""
        try:
            run_issuance = load_run_issuance()
        except WalletError as e:
            return {"format": vc_format, "ok": False, "error": str(e), "steps": [], "credential": None}
        result = run_issuance(vc_format, holder_key=self.key)
        if result.get("ok") and vc_format in PRESENTABLE:
            entry = self.store(vc_format, result["credential"], "Inji Certify (Chirayu's issuance flow)")
            result["wallet"] = {"stored": True, "bound_to_wallet_key": entry["bound_to_wallet_key"]}
        return result

    def receive_from_test_issuer(self, vc_format: str, issuer=None, **kw) -> dict:
        from test_issuer import TestIssuer
        issuer = issuer or TestIssuer()
        cred = issuer.issue(vc_format, self.did, **kw)
        entry = self.store(vc_format, cred, f"offline test issuer ({issuer.did[:32]}...)")
        return {"format": vc_format, "ok": True, "error": None, "credential": cred, "steps": [],
                "wallet": {"stored": True, "bound_to_wallet_key": entry["bound_to_wallet_key"]}}

    def import_credential(self, vc_format: str, credential) -> dict:
        if isinstance(credential, str) and vc_format == "ldp_vc":
            credential = json.loads(credential)
        return self.store(vc_format, credential, "imported")

    def summary(self) -> dict:
        creds = {}
        for fmt, e in self.credentials.items():
            c = e["credential"]
            if fmt == "ldp_vc":
                preview = {"type": c.get("type"), "issuer": c.get("issuer") if isinstance(c.get("issuer"), str) else (c.get("issuer") or {}).get("id"),
                           "claims": {k: v for k, v in (c.get("credentialSubject") or {}).items() if k not in ("id", "face")}}
            else:
                p = sdjwt.parse(c)
                view, _, _ = sdjwt.reconstruct(p["payload"], p["disclosures"])
                preview = {"vct": view.get("vct"), "issuer": view.get("iss"),
                           "claims": {k: v for k, v in (view.get("credentialSubject") or {}).items() if k not in ("id", "face")},
                           "selectively_disclosable": [d["name"] for d in p["disclosures"]]}
            creds[fmt] = {"source": e["source"], "received_at": e["received_at"],
                          "bound_to_wallet_key": e["bound_to_wallet_key"], "preview": preview}
        return {"holder_did": self.did, "holder_jwk": self.public_jwk, "key_type": "EC P-256 (ES256)", "credentials": creds}

    # ------------------------------------------------------------ presenting
    @staticmethod
    def read_request(authorization_request_uri: str) -> dict:
        """Parse openid4vp://authorize?..., fetching request_uri / presentation_definition_uri if used."""
        q = {k: v[0] for k, v in parse_qs(urlparse(authorization_request_uri).query).items()}
        if "request_uri" in q:
            r = requests.get(q["request_uri"], timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            body = r.text.strip()
            q = sdjwt.decode_jwt_part(body.split(".")[1]) if body.count(".") == 2 and not body.startswith("{") else r.json()
        if isinstance(q.get("presentation_definition"), str):
            q["presentation_definition"] = json.loads(q["presentation_definition"])
        if "presentation_definition_uri" in q and "presentation_definition" not in q:
            q["presentation_definition"] = requests.get(q["presentation_definition_uri"], timeout=REQUEST_TIMEOUT).json()
        if isinstance(q.get("client_metadata"), str):
            q["client_metadata"] = json.loads(q["client_metadata"])
        return q

    def credential_view(self, vc_format: str, credential) -> dict:
        if vc_format == "ldp_vc":
            return credential
        p = sdjwt.parse(credential)
        return sdjwt.reconstruct(p["payload"], p["disclosures"])[0]

    def match(self, request: dict, vc_format: str):
        """(descriptor, reasons it doesn't match) for the stored credential."""
        entry = self.credentials.get(vc_format)
        pd = request.get("presentation_definition") or {}
        descriptors = pd.get("input_descriptors") or []
        if not entry:
            return (descriptors[0] if descriptors else None), [f"no {vc_format} credential in the wallet"]
        view = self.credential_view(vc_format, entry["credential"])
        best = None
        for d in descriptors:
            reasons = []
            formats = pex.accepted_formats(pd, d, request.get("client_metadata"))
            if formats and vc_format not in formats and not (vc_format == "ldp_vc" and "ldp_vp" in formats):
                reasons.append(f"request accepts {formats}, credential is {vc_format}")
            reasons += pex.constraint_failures(d, view)
            if not reasons:
                return d, []
            if best is None or len(reasons) < len(best[1]):
                best = (d, reasons)
        return best if best else (None, ["the request has no input_descriptors"])

    def build_presentation(self, request: dict, vc_format: str, descriptor: dict, alter: bool = False) -> dict:
        """Returns {vp_token, presentation_submission, summary}. alter=True changes
        farmerID after issuance (a tampered credential), for the negative test."""
        entry = self.credentials.get(vc_format)
        if not entry:
            raise WalletError(f"no {vc_format} credential in the wallet")
        cred = copy.deepcopy(entry["credential"])
        pd = request.get("presentation_definition") or {}
        desc_id = (descriptor or {}).get("id", "credential")
        submission_id = str(uuid.uuid4())

        if vc_format == "ldp_vc":
            if alter:
                cred["credentialSubject"]["farmerID"] = ALTERED_FARMER_ID
            holder = self.holder_did_for(vc_format, entry["credential"])
            vp = {"@context": [CREDENTIALS_V1], "type": ["VerifiablePresentation"], "id": f"urn:uuid:{uuid.uuid4()}",
                  "holder": holder, "verifiableCredential": [cred]}
            signed = sign_jws2020(vp, self.key, holder + "#0", "authentication",
                                  challenge=request.get("nonce"), domain=request.get("client_id"))
            submission = {"id": submission_id, "definition_id": pd.get("id"), "descriptor_map": [{
                "id": desc_id, "format": "ldp_vp", "path": "$",
                "path_nested": {"id": desc_id, "format": "ldp_vc", "path": "$.verifiableCredential[0]"}}]}
            return {"vp_token": signed, "vp_token_string": json.dumps(signed, separators=(",", ":")),
                    "presentation_submission": submission,
                    "summary": {"proof_type": "JsonWebSignature2020 (ES256)", "holder": holder,
                                "challenge": request.get("nonce"), "domain": request.get("client_id"),
                                "altered": {"credentialSubject.farmerID": ALTERED_FARMER_ID} if alter else None}}

        if vc_format == "vc+sd-jwt":
            wanted = pex.referenced_claims(descriptor)

            def mutate(d):
                if alter and d["name"] == "farmerID":
                    enc = sdjwt.make_disclosure("farmerID", ALTERED_FARMER_ID, d["salt"])
                    return {**d, "encoded": enc, "value": ALTERED_FARMER_ID}
                return d

            out = sdjwt.present(cred, lambda name: name in wanted, self.key,
                                audience=request.get("client_id"), nonce=request.get("nonce"), mutate=mutate)
            submission = {"id": submission_id, "definition_id": pd.get("id"),
                          "descriptor_map": [{"id": desc_id, "format": "vc+sd-jwt", "path": "$"}]}
            return {"vp_token": out["presentation"], "vp_token_string": out["presentation"],
                    "presentation_submission": submission,
                    "summary": {"disclosed": out["disclosed"], "withheld": out["withheld"],
                                "kb_jwt": {"header": out["kb_header"], "payload": out["kb_payload"]},
                                "altered": {"farmerID disclosure": ALTERED_FARMER_ID} if alter else None}}
        raise WalletError(f"cannot present {vc_format} over OpenID4VP to Inji Verify 0.18.2")

    def submit(self, log, request: dict, presentation: dict, label="Wallet sends the presentation (direct_post)"):
        url = rewrite_url(request["response_uri"])
        form = {"vp_token": presentation["vp_token_string"],
                "presentation_submission": json.dumps(presentation["presentation_submission"], separators=(",", ":")),
                "state": request["state"]}
        shown = {**form, "vp_token": presentation["vp_token"]}
        try:
            r = requests.post(url, data=form, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            log.error(label, "wallet", "POST", url, e, request=shown)
            return None
        log.http(label, "wallet", "POST", url, r, request=shown,
                 note="The wallet posts vp_token + presentation_submission to the verifier's response_uri, "
                      "with state = the verifier's request id.")
        return r


def rewrite_url(url: str) -> str:
    """WALLET_URL_REWRITES="http://host.docker.internal:8082=http://localhost:8082" lets this wallet, running on
    the host, reach a response_uri that was chosen so that wallets inside Docker (Inji Web's Mimoto) can reach it."""
    for pair in filter(None, os.environ.get("WALLET_URL_REWRITES", "").split(",")):
        src, _, dst = pair.partition("=")  # a base URL has no "=" in it
        if src and url.startswith(src.strip()):
            return dst.strip() + url[len(src.strip()):]
    return url


def load_run_issuance():
    """Import Chirayu's run_issuance and make sure it has the holder_key patch."""
    if not os.path.isdir(CERTIFY_SCRIPTS_DIR):
        raise WalletError(f"Certify scripts not found at {CERTIFY_SCRIPTS_DIR}. Put verify/ next to certify/, "
                          "or set CERTIFY_SCRIPTS_DIR.")
    if CERTIFY_SCRIPTS_DIR not in sys.path:
        sys.path.insert(0, CERTIFY_SCRIPTS_DIR)
    try:
        import issuance_flow  # noqa: WPS433 (Chirayu's module)
    except ImportError as e:
        raise WalletError(f"could not import certify/scripts/issuance_flow.py: {e}")
    fn = issuance_flow.run_issuance
    if "holder_key" not in inspect.signature(fn).parameters:
        raise WalletError("certify/scripts/issuance_flow.py does not accept holder_key yet, so the credential "
                          "would be bound to a key the wallet never sees. Apply issuance_flow_holder_key.patch "
                          "(see verify/README.md, 'Setup').")
    return fn
