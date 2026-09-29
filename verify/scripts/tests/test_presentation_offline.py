#!/usr/bin/env python3
"""
Offline tests: no Docker, no network. Covers the crypto, the wallet, the
independent checks and the whole flow against a model of Inji Verify.

    cd verify/scripts
    ALLOW_REMOTE_CONTEXTS=0 python3 -m unittest discover -s tests -v
"""
import base64
import copy
import hashlib
import json
import os
import shutil
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault("ALLOW_REMOTE_CONTEXTS", "0")

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec, ed25519  # noqa: E402

import checks  # noqa: E402
import pex  # noqa: E402
import presentation_flow  # noqa: E402
import sdjwt  # noqa: E402
import verifier_client  # noqa: E402
import wallet as wallet_mod  # noqa: E402
from did_resolver import did_jwk, jwk_of_did, jwk_to_public_key, resolve_key, same_key, public_key_to_jwk  # noqa: E402
from jsonld_proofs import (CREDENTIALS_V1, b58decode, b58encode, sign_ed25519_2020, sign_jws2020,  # noqa: E402
                           verify_ed25519_2020, verify_jws2020)
sys.path.insert(0, HERE)
from fake_inji_verify import FakeInjiVerify  # noqa: E402
from test_issuer import TestIssuer  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "external_signed_vp.json")

# Chirayu's docs/did.json (published issuer DID document), verbatim keys
CERTIFY_DID_DOC = {
    "id": "did:web:mushmat.github.io:inji-did",
    "verificationMethod": [
        {"id": "did:web:mushmat.github.io:inji-did#9D8PhzBlEc3-5jQ5vlkWR_4Tk33ZdD4OU_uFb9NUoss",
         "type": "EcdsaSecp256r1VerificationKey2019", "publicKeyMultibase": "zDnaen22rRZSiPiYAsQv59UjoFyW1Wuf7CioHtAHCVwLXVRUD"},
        {"id": "did:web:mushmat.github.io:inji-did#bQSVQEnCj599B4J5asw0bCxcBZR_d-Tx8u0S9wHJyUw",
         "type": "Ed25519VerificationKey2020", "publicKeyMultibase": "z6MknS7pkCBNN9iFyQdbgP88xBUaQkcsxc5nP3uwUwFGtnR6"},
    ],
}


class ExternalFixtureTest(unittest.TestCase):
    """Signed by other implementations (Digital Bazaar jsonld-signatures, and a
    JsonWebSignature2020 signer written from @transmute's algorithm)."""

    @classmethod
    def setUpClass(cls):
        with open(FIXTURE) as f:
            cls.fx = json.load(f)

    def test_issuer_signature_from_jsonld_signatures_verifies(self):
        vc = self.fx["vp"]["verifiableCredential"][0]
        raw = b58decode(self.fx["issuerPublicKeyMultibase"][1:])[2:]
        self.assertTrue(verify_ed25519_2020(vc, ed25519.Ed25519PublicKey.from_public_bytes(raw)))

    def test_holder_jws2020_from_independent_signer_verifies(self):
        key = jwk_to_public_key(self.fx["holderJwk"])
        self.assertTrue(verify_jws2020(self.fx["vp"], key))

    def test_tampering_breaks_both(self):
        vp = copy.deepcopy(self.fx["vp"])
        vp["verifiableCredential"][0]["credentialSubject"]["farmerID"] = "000000000"
        raw = b58decode(self.fx["issuerPublicKeyMultibase"][1:])[2:]
        self.assertFalse(verify_ed25519_2020(vp["verifiableCredential"][0], ed25519.Ed25519PublicKey.from_public_bytes(raw)))
        self.assertFalse(verify_jws2020(vp, jwk_to_public_key(self.fx["holderJwk"])))

    def test_wrong_challenge_breaks_holder_proof(self):
        vp = copy.deepcopy(self.fx["vp"])
        vp["proof"]["challenge"] = "other"
        self.assertFalse(verify_jws2020(vp, jwk_to_public_key(self.fx["holderJwk"])))


class ProofRoundTripTest(unittest.TestCase):
    DOC = {"@context": [CREDENTIALS_V1], "type": ["VerifiablePresentation"], "holder": "did:example:h"}

    def test_jws2020_es256_and_eddsa(self):
        for key in (ec.generate_private_key(ec.SECP256R1()), ed25519.Ed25519PrivateKey.generate()):
            signed = sign_jws2020(self.DOC, key, "did:example:h#0", "authentication", challenge="n", domain="d")
            self.assertTrue(verify_jws2020(signed, key.public_key()))
            self.assertTrue(signed["proof"]["jws"].split(".")[1] == "", "JWS must be detached")
            other = ec.generate_private_key(ec.SECP256R1()) if isinstance(key, ec.EllipticCurvePrivateKey) else ed25519.Ed25519PrivateKey.generate()
            self.assertFalse(verify_jws2020(signed, other.public_key()))

    def test_ed25519_2020(self):
        key = ed25519.Ed25519PrivateKey.generate()
        signed = sign_ed25519_2020(self.DOC, key, "did:example:i#1")
        self.assertTrue(signed["proof"]["proofValue"].startswith("z"))
        self.assertTrue(verify_ed25519_2020(signed, key.public_key()))

    def test_base58_roundtrip_keeps_leading_zeros(self):
        for data in (b"\x00\x00abc", b"", os.urandom(40)):
            self.assertEqual(b58decode(b58encode(data)), data)


class DidResolverTest(unittest.TestCase):
    def test_did_jwk_roundtrip(self):
        key = ec.generate_private_key(ec.SECP256R1()).public_key()
        self.assertTrue(same_key(jwk_of_did(did_jwk(key)), public_key_to_jwk(key)))

    def test_did_jwk_with_extra_members_still_same_key(self):
        # Certify builds did:jwk from the proof header's jwk, which has alg/use too
        key = ec.generate_private_key(ec.SECP256R1()).public_key()
        jwk = {**public_key_to_jwk(key), "alg": "ES256", "use": "sig"}
        did = "did:jwk:" + base64.urlsafe_b64encode(json.dumps(jwk).encode()).rstrip(b"=").decode()
        self.assertTrue(same_key(jwk_of_did(did), public_key_to_jwk(key)))

    def test_did_web_certify_document_both_key_types(self):
        fetch = lambda url: CERTIFY_DID_DOC  # noqa: E731
        k1, info = resolve_key(CERTIFY_DID_DOC["verificationMethod"][0]["id"], fetch)
        self.assertIsInstance(k1, ec.EllipticCurvePublicKey)  # zDn... = compressed P-256
        self.assertEqual(info["fetched_from"], "https://mushmat.github.io/inji-did/did.json")
        k2, _ = resolve_key(CERTIFY_DID_DOC["id"], fetch, alg="EdDSA")  # no fragment: pick by alg
        self.assertIsInstance(k2, ed25519.Ed25519PublicKey)

    def test_did_key_ed25519(self):
        issuer = TestIssuer()
        key, _ = resolve_key(issuer.verification_method)
        self.assertTrue(same_key(public_key_to_jwk(key), public_key_to_jwk(issuer.key.public_key())))


class SdJwtTest(unittest.TestCase):
    def setUp(self):
        self.holder = ec.generate_private_key(ec.SECP256R1())
        self.issuer = TestIssuer()
        self.token = self.issuer.issue_sd_jwt(did_jwk(self.holder.public_key()), sd_claims=("farmerID", "mobileNumber"))

    def test_nested_disclosures_reconstruct(self):
        p = sdjwt.parse(self.token)
        self.assertNotIn("farmerID", p["payload"]["credentialSubject"])
        view, unmatched, paths = sdjwt.reconstruct(p["payload"], p["disclosures"])
        self.assertEqual(view["credentialSubject"]["farmerID"], "987654321")
        self.assertEqual(paths["farmerID"], "$.credentialSubject.farmerID")
        self.assertEqual(unmatched, [])

    def test_present_selected_claims_with_key_binding(self):
        out = sdjwt.present(self.token, lambda n: n == "farmerID", self.holder, "client", "nonce-1")
        p = sdjwt.parse(out["presentation"])
        self.assertEqual([d["name"] for d in p["disclosures"]], ["farmerID"])
        self.assertEqual(out["withheld"], ["mobileNumber"])
        session = {"nonce": "nonce-1", "client_id": "client", "presentation_definition": pex.build_presentation_definition("vc+sd-jwt")}
        results = {c["id"]: c["ok"] for c in checks.check_sd_jwt(session, out["presentation"])}
        for cid in ("issuer_signature", "disclosures", "kb_signature", "kb_nonce", "kb_aud", "kb_sd_hash", "constraints"):
            self.assertTrue(results[cid], cid)

    def test_tampered_disclosure_is_caught(self):
        def mutate(d):
            return {**d, "encoded": sdjwt.make_disclosure(d["name"], "000000000", d["salt"])}
        out = sdjwt.present(self.token, lambda n: n == "farmerID", self.holder, "c", "n", mutate=mutate)
        session = {"nonce": "n", "client_id": "c", "presentation_definition": pex.build_presentation_definition("vc+sd-jwt")}
        results = {c["id"]: c["ok"] for c in checks.check_sd_jwt(session, out["presentation"])}
        self.assertFalse(results["disclosures"])
        self.assertTrue(results["kb_sd_hash"], "KB still covers what was sent; only the digest check catches this")

    def test_removing_a_disclosure_after_kb_breaks_sd_hash(self):
        out = sdjwt.present(self.token, lambda n: True, self.holder, "c", "n")
        parts = out["presentation"].split("~")
        stripped = "~".join([parts[0]] + parts[2:])
        session = {"nonce": "n", "client_id": "c", "presentation_definition": pex.build_presentation_definition("vc+sd-jwt")}
        results = {c["id"]: c["ok"] for c in checks.check_sd_jwt(session, stripped)}
        self.assertFalse(results["kb_sd_hash"])


class PresentationDefinitionTest(unittest.TestCase):
    def test_ldp_type_pattern(self):
        vc = {"type": ["VerifiableCredential", "FarmerCredential"]}
        d = pex.build_presentation_definition("ldp_vc")["input_descriptors"][0]
        self.assertEqual(pex.constraint_failures(d, vc), [])
        wrong = pex.build_presentation_definition("ldp_vc", pex.WRONG_TYPE)["input_descriptors"][0]
        self.assertEqual(len(pex.constraint_failures(wrong, vc)), 1)

    def test_sd_jwt_needs_vct_and_disclosed_farmer_id(self):
        d = pex.build_presentation_definition("vc+sd-jwt")["input_descriptors"][0]
        self.assertEqual(pex.referenced_claims(d), {"farmerID"})
        view = {"vct": "FarmerCredentialSdJwt", "credentialSubject": {}}
        self.assertIn("$.credentialSubject.farmerID is missing", pex.constraint_failures(d, view))

    def test_only_fields_inji_verify_keeps(self):
        """Filters use only type + pattern, which is all Inji Verify's FilterDTO has (F4)."""
        for fmt in ("ldp_vc", "vc+sd-jwt"):
            for f in pex.build_presentation_definition(fmt)["input_descriptors"][0]["constraints"]["fields"]:
                self.assertLessEqual(set(f), {"path", "filter"})
                self.assertLessEqual(set(f.get("filter", {})), {"type", "pattern"})


class VerifierContractTest(unittest.TestCase):
    def test_request_uri_matches_inji_verify_sdk(self):
        c = verifier_client.VerifierClient("http://v/v1/verify", "my-client")
        uri = c.authorization_request_uri({"requestId": "req1", "authorizationDetails": {
            "responseMode": "direct_post", "responseType": "vp_token", "nonce": "n1",
            "responseUri": "http://v/v1/verify/vp-submission/direct-post", "presentationDefinition": {"id": "pd"}}})
        req = wallet_mod.HolderWallet.read_request(uri)
        self.assertTrue(uri.startswith("openid4vp://authorize?"))
        self.assertEqual(req["state"], "req1")
        self.assertEqual(req["client_id"], "my-client")
        self.assertEqual(req["presentation_definition"], {"id": "pd"})
        self.assertIn("ldp_vp", req["client_metadata"]["vp_formats"])

    def test_request_uri_variant(self):
        c = verifier_client.VerifierClient("http://v", "cid")
        uri = c.authorization_request_uri({"requestId": "r", "requestUri": "http://v/req/r", "authorizationDetails": {}})
        self.assertIn("request_uri=", uri)
        self.assertNotIn("presentation_definition", uri)

    def test_map_v2(self):
        body = {"allChecksSuccessful": False, "credentialResults": [{
            "holderProofCheck": {"valid": True}, "schemaAndSignatureCheck": {"valid": False, "error": {"errorCode": "ERR_SIGNATURE_VERIFICATION_FAILED"}},
            "expiryCheck": None, "statusCheck": [], "claims": {}}]}
        r = verifier_client.map_v2(body)
        self.assertEqual(r["status"], "INVALID")
        self.assertIn("ERR_SIGNATURE_VERIFICATION_FAILED", r["detail"])
        ok = verifier_client.map_v2({"allChecksSuccessful": True, "credentialResults": [{"schemaAndSignatureCheck": {"valid": True}, "expiryCheck": {"valid": True}}]})
        self.assertEqual(ok["status"], "VALID")
        exp = verifier_client.map_v2({"allChecksSuccessful": False, "credentialResults": [{"schemaAndSignatureCheck": {"valid": True}, "expiryCheck": {"valid": False}}]})
        self.assertEqual(exp["status"], "EXPIRED")
        self.assertEqual(verifier_client.map_v2({"allChecksSuccessful": True, "credentialResults": []})["status"], "INVALID")

    def test_map_v1(self):
        self.assertEqual(verifier_client.map_v1({"vpResultStatus": "SUCCESS", "vcResults": [{"verificationStatus": "SUCCESS"}]})["status"], "VALID")
        self.assertEqual(verifier_client.map_v1({"vpResultStatus": "FAILED", "vcResults": [{"verificationStatus": "EXPIRED"}]})["status"], "EXPIRED")
        self.assertEqual(verifier_client.map_v1({"vpResultStatus": "FAILED", "vcResults": [{"verificationStatus": "INVALID"}]})["status"], "INVALID")


class WalletTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_key_persists(self):
        a = wallet_mod.HolderWallet(os.path.join(self.dir, "w"))
        b = wallet_mod.HolderWallet(os.path.join(self.dir, "w"))
        self.assertEqual(a.did, b.did)

    def test_unpatched_issuance_flow_gives_a_clear_error(self):
        scripts = os.path.join(self.dir, "unpatched")
        os.makedirs(scripts)
        with open(os.path.join(scripts, "issuance_flow.py"), "w") as f:
            f.write("def run_issuance(vc_format):\n    return {}\n")
        with _certify_dir(scripts):
            with self.assertRaises(wallet_mod.WalletError) as cm:
                wallet_mod.load_run_issuance()
        self.assertIn("issuance_flow_holder_key.patch", str(cm.exception))

    def test_receive_from_certify_passes_the_wallet_key(self):
        """A stand-in for Chirayu's patched run_issuance that binds to holder_key the way Certify does
        (did:jwk of the proof-header JWK, which carries alg and use)."""
        scripts = os.path.join(self.dir, "patched")
        os.makedirs(scripts)
        with open(os.path.join(scripts, "issuance_flow.py"), "w") as f:
            f.write(textwrap.dedent("""
                import base64, json
                from jwt.algorithms import ECAlgorithm
                from test_issuer import TestIssuer
                def run_issuance(vc_format, holder_key=None):
                    jwk = json.loads(ECAlgorithm.to_jwk(holder_key.public_key())); jwk.update(alg="ES256", use="sig")
                    did = "did:jwk:" + base64.urlsafe_b64encode(json.dumps(jwk).encode()).decode()  # padded, like Certify
                    return {"ok": True, "error": None, "steps": [{"name": "Request the credential", "method": "POST",
                            "url": "http://certify", "status": 200, "ok": True, "response": {}}],
                            "credential": TestIssuer().issue(vc_format, did), "holder_jwk": jwk}
            """))
        with _certify_dir(scripts):
            w = wallet_mod.HolderWallet(os.path.join(self.dir, "w"))
            result = w.receive_from_certify("ldp_vc")
        self.assertTrue(result["ok"], result.get("error"))
        self.assertTrue(result["wallet"]["bound_to_wallet_key"])
        cred = w.credentials["ldp_vc"]["credential"]
        self.assertEqual(w.holder_did_for("ldp_vc", cred), cred["credentialSubject"]["id"].rstrip("="))
        self.assertNotIn("=", w.holder_did_for("ldp_vc", cred), "did:jwk must be unpadded base64url (F9)")
        self.assertNotEqual(w.holder_did_for("ldp_vc", cred), w.did, "keeps Certify's JWK members (alg/use), not a re-encoding")


class _certify_dir:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        self.old = wallet_mod.CERTIFY_SCRIPTS_DIR
        wallet_mod.CERTIFY_SCRIPTS_DIR = self.path
        sys.modules.pop("issuance_flow", None)

    def __exit__(self, *exc):
        wallet_mod.CERTIFY_SCRIPTS_DIR = self.old
        sys.modules.pop("issuance_flow", None)
        if self.path in sys.path:
            sys.path.remove(self.path)


class FlowAgainstModelOfInjiVerifyTest(unittest.TestCase):
    """End to end through HTTP against fake_inji_verify (a model of 0.18.2)."""

    EXPECT = {
        # (format, scenario): (Inji Verify says, verdict, gap finding)
        ("ldp_vc", "none"): ("VALID", "PASS", None),
        ("ldp_vc", "altered"): ("INVALID", "PASS", None),
        ("ldp_vc", "replay"): ("REJECTED", "PASS", None),         # challenge checked at submission
        ("ldp_vc", "wrong_type"): ("VALID", "FAIL", ["F2"]),
        ("vc+sd-jwt", "none"): ("VALID", "PASS", None),
        ("vc+sd-jwt", "altered"): ("INVALID", "PASS", None),
        ("vc+sd-jwt", "replay"): ("VALID", "FAIL", ["F3"]),       # KB nonce not compared
        ("vc+sd-jwt", "wrong_type"): ("VALID", "FAIL", ["F2"]),
        ("ldp_vc", "forged_issuer"): ("VALID", "FAIL", ["F10"]),  # key taken from any verificationMethod
        ("vc+sd-jwt", "forged_issuer"): ("VALID", "FAIL", ["F10"]),  # key taken from a self-signed x5c
        ("ldp_vc", "expired"): ("EXPIRED", "PASS", None),
        ("vc+sd-jwt", "expired"): ("EXPIRED", "PASS", None),
    }

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        cls.fake = FakeInjiVerify().__enter__()
        # the forged-issuer check looks up Certify's real keys; the fake serves a stand-in DID document
        from test_issuer import TestIssuer as _TI
        real = _TI()
        cls.fake.certify_did_document["verificationMethod"] = [{"id": "did:web:mushmat.github.io:inji-did#k",
                                                                "publicKeyMultibase": real.multibase}]
        cls._old_did_url = checks.CERTIFY_DID_DOCUMENT_URL
        checks.CERTIFY_DID_DOCUMENT_URL = cls.fake.base.replace("/v1/verify", "/certify/did.json")
        cls.wallet = wallet_mod.HolderWallet(cls.dir)
        issuer = TestIssuer()
        for fmt in ("ldp_vc", "vc+sd-jwt"):
            cls.wallet.receive_from_test_issuer(fmt, issuer)

    @classmethod
    def tearDownClass(cls):
        checks.CERTIFY_DID_DOCUMENT_URL = cls._old_did_url
        cls.fake.__exit__()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def run_case(self, fmt, scenario):
        verifier = verifier_client.VerifierClient(self.fake.base, "playground-test")
        return presentation_flow.run_presentation(fmt, scenario, source="wallet", wallet=self.wallet, verifier=verifier)

    def test_all_scenarios(self):
        for (fmt, scenario), (says, verdict, finding) in self.EXPECT.items():
            with self.subTest(format=fmt, scenario=scenario):
                r = self.run_case(fmt, scenario)
                self.assertTrue(r["ok"], r.get("error"))
                self.assertEqual(r["verifier_result"]["status"], says, r["verifier_result"])
                self.assertEqual(r["outcome"]["verdict"], verdict)
                if finding:
                    self.assertEqual(r["suspected_gaps"][0]["finding"], finding)
                else:
                    self.assertEqual(r["suspected_gaps"], [])
                self.assertTrue(all("name" in s and "ok" in s for s in r["steps"]))

    def test_honest_presentation_passes_every_independent_check(self):
        for fmt in ("ldp_vc", "vc+sd-jwt"):
            r = self.run_case(fmt, "none")
            failed = [c for c in r["playground_checks"] if c["ok"] is not True]
            self.assertEqual(failed, [], fmt)

    def test_sd_jwt_discloses_only_what_was_asked(self):
        r = self.run_case("vc+sd-jwt", "none")
        self.assertEqual(r["presentation"]["disclosed"], [{"farmerID": "987654321"}])

    def test_mdoc_is_explained_not_attempted(self):
        r = presentation_flow.run_presentation("mso_mdoc", wallet=self.wallet)
        self.assertFalse(r["ok"])
        self.assertIn("processSingleToken", r["error"])
        self.assertEqual(r["steps"], [])

    def test_verifier_down_is_a_clean_error(self):
        v = verifier_client.VerifierClient("http://127.0.0.1:9/v1/verify", "x")
        r = presentation_flow.run_presentation("ldp_vc", "none", source="wallet", wallet=self.wallet, verifier=v)
        self.assertFalse(r["ok"])
        self.assertEqual(r["steps"][-1]["status"], None)

    def test_phone_mode(self):
        v = verifier_client.VerifierClient(self.fake.base, "playground-test")
        started = presentation_flow.start_phone_session("vc+sd-jwt", verifier=v)
        self.assertTrue(started["ok"])
        self.assertTrue(started["qr"] is None or started["qr"].startswith("data:image/svg+xml;base64,"))
        self.assertFalse(presentation_flow.poll_phone_session(started["id"])["done"])
        # the "phone": our wallet answering the scanned link
        req = self.wallet.read_request(started["authorization_request_uri"])
        d, _ = self.wallet.match(req, "vc+sd-jwt")
        p = self.wallet.build_presentation(req, "vc+sd-jwt", d)
        from steps import StepLog
        self.wallet.submit(StepLog(), req, p)
        done = presentation_flow.poll_phone_session(started["id"])
        self.assertTrue(done["done"])
        self.assertEqual(done["verifier_result"]["status"], "VALID")
        self.assertEqual(done["outcome"]["verdict"], "PASS")
        ran = {c["id"] for c in done["playground_checks"] if c["ok"] is not None}
        self.assertIn("issuer_signature", ran)


if __name__ == "__main__":
    unittest.main()
