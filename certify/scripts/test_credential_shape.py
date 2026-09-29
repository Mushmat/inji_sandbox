#!/usr/bin/env python3
"""
Real assertions on the issued credentials, not just "it returned 200".
Needs Certify running locally (../docker-compose/) - these are integration
tests against the real flow, not offline unit tests.

Usage:
    python3 -m unittest test_credential_shape.py -v
"""
import unittest

import issuance_flow
from identity_store import read_identity
from issuance_flow import run_issuance


class JsonLdCredentialTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_issuance("ldp_vc")

    def test_flow_succeeded(self):
        self.assertTrue(self.result["ok"], self.result.get("error"))

    def test_every_step_was_200(self):
        for step in self.result["steps"]:
            self.assertEqual(step["status"], 200, step["name"])

    def test_credential_type_and_proof(self):
        cred = self.result["credential"]
        self.assertIn("FarmerCredential", cred["type"])
        self.assertIn("VerifiableCredential", cred["type"])
        self.assertEqual(cred["proof"]["type"], "Ed25519Signature2020")
        self.assertEqual(cred["proof"]["proofPurpose"], "assertionMethod")

    def test_issuer_is_our_did(self):
        cred = self.result["credential"]
        self.assertTrue(cred["issuer"].startswith("did:web:"))

    def test_subject_has_expected_claims(self):
        subject = self.result["credential"]["credentialSubject"]
        for field in ("fullName", "farmerID", "state", "district"):
            self.assertIn(field, subject)


class SdJwtCredentialTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_issuance("vc+sd-jwt")

    def test_flow_succeeded(self):
        self.assertTrue(self.result["ok"], self.result.get("error"))

    def test_header_and_vct(self):
        decoded = self.result["credential_decoded"]
        self.assertEqual(decoded["header"]["typ"], "vc+sd-jwt")
        self.assertEqual(decoded["header"]["alg"], "EdDSA")
        self.assertEqual(decoded["payload"]["vct"], "FarmerCredentialSdJwt")

    def test_holder_binding_present(self):
        payload = self.result["credential_decoded"]["payload"]
        self.assertIn("cnf", payload)
        self.assertTrue(payload["cnf"]["kid"].startswith("did:jwk:"))

    def test_farmer_id_is_selectively_disclosable(self):
        payload = self.result["credential_decoded"]["payload"]
        disclosures = self.result["credential_decoded"]["disclosures"]
        # farmerID shouldn't be sitting in the plaintext payload...
        self.assertNotIn("farmerID", payload["credentialSubject"])
        # ...only reachable through its disclosure
        names = [d[1] for d in disclosures]
        self.assertIn("farmerID", names)
        farmer_id_disclosure = next(d for d in disclosures if d[1] == "farmerID")
        # whatever the identity editor last saved, not a fixed value
        self.assertEqual(farmer_id_disclosure[2], read_identity()["farmerID"])


class MDocCredentialTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_issuance("mso_mdoc")

    def test_flow_succeeded(self):
        self.assertTrue(self.result["ok"], self.result.get("error"))

    def test_doctype_and_signed(self):
        decoded = self.result["credential_decoded"]
        self.assertEqual(decoded["docType"], "org.iso.18013.5.1.mDL")
        self.assertTrue(decoded["signed"])

    def test_claims_present(self):
        claims = self.result["credential_decoded"]["claims"]["org.iso.18013.5.1"]
        for field in ("family_name", "given_name", "birth_date", "document_number"):
            self.assertIn(field, claims)
        # confirms the CSV columns actually got substituted, not left as
        # literal "${...}" template text
        self.assertNotIn("$", claims["family_name"])


class InvalidInputTest(unittest.TestCase):
    def test_unknown_format_fails_cleanly(self):
        result = run_issuance("not-a-real-format")
        self.assertFalse(result["ok"])
        self.assertIn("unknown format", result["error"])
        self.assertEqual(result["steps"], [])


class NetworkFailureTest(unittest.TestCase):
    def test_unreachable_auth_server_fails_cleanly(self):
        original = issuance_flow.AUTH_SERVER
        issuance_flow.AUTH_SERVER = "https://this-host-should-not-resolve.invalid/v1/esignet"
        try:
            result = run_issuance("ldp_vc")
        finally:
            issuance_flow.AUTH_SERVER = original

        self.assertFalse(result["ok"])
        self.assertIn("network error", result["error"])


if __name__ == "__main__":
    unittest.main()
