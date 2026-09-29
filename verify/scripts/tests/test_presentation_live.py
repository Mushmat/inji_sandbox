#!/usr/bin/env python3
"""
Live tests against the real Inji Verify container (and Certify, through
Chirayu's issuance flow). Skipped unless both answer.

    cd verify/scripts
    python3 -m unittest tests.test_presentation_live -v      # or: discover -s tests

The honest and altered cases must come out right. Replay and wrong-type are
the open questions (F2, F3): these tests record what Inji Verify does and
print it, and fail only if the flow itself breaks. Paste the printed table
into docs/FINDINGS.md.
"""
import os
import sys
import unittest

import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from presentation_flow import run_presentation  # noqa: E402
from verifier_client import VerifierClient  # noqa: E402
from wallet import HolderWallet, WalletError, load_run_issuance  # noqa: E402

CERTIFY_WELL_KNOWN = os.environ.get("CERTIFY_WELL_KNOWN", "http://localhost:8090/v1/certify/.well-known/openid-credential-issuer")


def _certify_up():
    try:
        return requests.get(CERTIFY_WELL_KNOWN, timeout=4).status_code == 200
    except requests.RequestException:
        return False


VERIFY_UP = VerifierClient().health()["ok"]
CERTIFY_UP = _certify_up()
try:
    load_run_issuance()
    PATCHED, PATCH_MSG = True, ""
except WalletError as e:
    PATCHED, PATCH_MSG = False, str(e)


@unittest.skipUnless(VERIFY_UP, "Inji Verify is not reachable (start verify/docker-compose)")
@unittest.skipUnless(CERTIFY_UP, "Inji Certify is not reachable (start certify/docker-compose)")
@unittest.skipUnless(PATCHED, PATCH_MSG or "issuance_flow.py needs the holder_key patch")
class LivePresentationTest(unittest.TestCase):
    table = []

    @classmethod
    def setUpClass(cls):
        cls.wallet = HolderWallet()
        for fmt in ("ldp_vc", "vc+sd-jwt"):
            r = cls.wallet.receive_from_certify(fmt)
            if not r["ok"]:
                raise unittest.SkipTest(f"could not get a {fmt} credential from Certify: {r['error']}")

    @classmethod
    def tearDownClass(cls):
        print("\n\n  format     scenario     expected  Inji Verify  verdict  gap")
        for row in cls.table:
            print("  " + "  ".join(row))

    def run_case(self, fmt, scenario):
        r = run_presentation(fmt, scenario, source="wallet", wallet=self.wallet)
        self.assertTrue(r["ok"], r.get("error"))
        o = r["outcome"]
        gap = ",".join(f for g in r["suspected_gaps"] for f in (g.get("finding") or ["?"]))
        self.table.append((f"{fmt:9}", f"{scenario:11}", f"{o['expected']:8}", f"{o['result']:11}", f"{o['verdict']:7}", gap))
        return r

    def test_honest_ldp(self):
        r = self.run_case("ldp_vc", "none")
        self.assertEqual(r["verifier_result"]["status"], "VALID", r["verifier_result"])

    def test_honest_sd_jwt(self):
        r = self.run_case("vc+sd-jwt", "none")
        self.assertEqual(r["verifier_result"]["status"], "VALID", r["verifier_result"])

    def test_altered(self):
        for fmt in ("ldp_vc", "vc+sd-jwt"):
            with self.subTest(fmt):
                self.assertEqual(self.run_case(fmt, "altered")["outcome"]["verdict"], "PASS")

    def test_record_open_questions(self):
        for fmt in ("ldp_vc", "vc+sd-jwt"):
            for sc in ("replay", "wrong_type"):
                with self.subTest(format=fmt, scenario=sc):
                    self.run_case(fmt, sc)


if __name__ == "__main__":
    unittest.main()
