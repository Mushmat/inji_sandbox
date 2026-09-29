"""The Playground's own rules: which combinations run, what counts as valid person data, and the report."""

import _env  # noqa: F401  (must come first)

import unittest

from fastapi.testclient import TestClient

import catalog
import identity
import main
import report

client = TestClient(main.app)


class Compatibility(unittest.TestCase):
    def check(self, issuer="certify_preauth", wallet="playground_wallet", verifier="inji_verify", fmt="ldp_vc", scenario="none"):
        return catalog.check(issuer, wallet, verifier, fmt, scenario)

    def test_default_combination_runs(self):
        self.assertEqual(self.check(), {"runnable": True, "blockers": [], "limits": []})

    def test_mdoc_issues_but_is_recorded_as_unsupported_by_inji_verify(self):
        c = self.check(issuer="certify", fmt="mso_mdoc")
        self.assertTrue(c["runnable"])
        self.assertTrue(any("M1" in l for l in c["limits"]))

    def test_inji_web_cannot_take_mdoc(self):
        self.assertFalse(self.check(issuer="certify", wallet="inji_web", fmt="mso_mdoc")["runnable"])

    def test_inji_web_cannot_run_tamper_scenarios(self):
        self.assertFalse(self.check(issuer="certify", wallet="inji_web", scenario="altered")["runnable"])

    def test_inji_web_needs_the_esignet_issuer(self):
        self.assertFalse(self.check(wallet="inji_web")["runnable"])
        self.assertFalse(self.check(issuer="test_issuer", wallet="inji_web")["runnable"])

    def test_inji_web_sd_jwt_runs_with_the_known_limit(self):
        c = self.check(issuer="certify", wallet="inji_web", fmt="vc+sd-jwt")
        self.assertTrue(c["runnable"])
        self.assertTrue(any("W5" in l for l in c["limits"]))

    def test_every_catalog_entry_is_checkable(self):
        for i in catalog.ISSUERS:
            for w in catalog.WALLETS:
                for v in catalog.VERIFIERS:
                    for f in catalog.FORMATS:
                        c = catalog.check(i, w, v, f, "none")
                        self.assertEqual(c["runnable"], not c["blockers"], (i, w, v, f))


class PersonData(unittest.TestCase):
    good = {"fullName": "Tortus Tortoise", "farmerID": "123748599", "mobileNumber": "9998882226",
            "postalCode": "560100", "dateOfBirth": "11-11-1999", "gender": "Female"}

    def test_good_data_passes(self):
        self.assertEqual(identity.validate(self.good), {})

    def test_farmer_id_is_nine_digits(self):
        for bad in ("12345678", "1234567890", "12345678a", ""):
            self.assertIn("farmerID", identity.validate({"farmerID": bad}), bad)

    def test_mobile_and_pin_follow_indian_formats(self):
        self.assertIn("mobileNumber", identity.validate({"mobileNumber": "5998882226"}))
        self.assertIn("postalCode", identity.validate({"postalCode": "060100"}))

    def test_date_of_birth_must_be_real_and_past(self):
        for bad in ("31-02-2000", "2000-01-01", "01-01-2999", "01-01-1850"):
            self.assertIn("dateOfBirth", identity.validate({"dateOfBirth": bad}), bad)

    def test_photo_must_be_an_image(self):
        self.assertIn("face", identity.validate({"face": "https://example.com/me.jpg"}))
        self.assertNotIn("face", identity.validate({"face": "data:image/jpeg;base64,AAAA"}))

    def test_api_refuses_bad_data_without_saving(self):
        before = client.get("/api/identity").json()["identity"]
        r = client.put("/api/identity", json={"fields": {"farmerID": "12"}})
        self.assertEqual(r.status_code, 422)
        self.assertIn("farmerID", r.json()["detail"]["errors"])
        self.assertEqual(client.get("/api/identity").json()["identity"], before)


class Api(unittest.TestCase):
    def test_catalog_lists_all_roles(self):
        body = client.get("/api/catalog").json()
        self.assertIn("certify_preauth", body["issuers"])
        self.assertIn("playground_verifier", body["verifiers"])

    def test_blocked_combination_is_refused_with_the_reason(self):
        r = client.post("/api/runs", json={"issuer": "test_issuer", "wallet": "inji_web", "verifier": "inji_verify",
                                           "format": "ldp_vc", "scenario": "none"})
        self.assertEqual(r.status_code, 422)
        self.assertIn("mimoto-issuers-config.json", r.json()["detail"])

    def test_unknown_run_is_404(self):
        self.assertEqual(client.get("/api/runs/nope").status_code, 404)


class Report(unittest.TestCase):
    def run_row(self, verdict, fmt="ldp_vc", scenario="none", ms=4000):
        return {"id": verdict + fmt + scenario, "created_at": "2026-09-29T10:00:00", "status": "done",
                "issuer": "certify_preauth", "wallet": "playground_wallet", "verifier": "inji_verify",
                "format": fmt, "scenario": scenario, "proof_type": "Ed25519Signature2020",
                "outcome": {"expected": "VALID", "result": "VALID", "verdict": verdict}, "error": None,
                "versions": {"Inji Verify": "0.18.2"}, "suspected_gaps": [], "unsupported": None,
                "duration_ms": ms, "timings": {"issue_ms": ms // 2, "present_verify_ms": ms // 2}}

    def test_report_has_matrix_flow_health_and_every_run(self):
        md = report.markdown([self.run_row("PASS"), self.run_row("FAIL", scenario="replay"), self.run_row("PASS", ms=6000)])
        for section in ("## Matrix", "## Flow health", "## Every run", "Inji Verify 0.18.2"):
            self.assertIn(section, md)
        self.assertIn("| 3 | 100% | 67% |", md)  # 3 runs, all completed, 2 of 3 correct


if __name__ == "__main__":
    unittest.main()
