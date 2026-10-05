"""The Playground verifier (FR8), end to end over real HTTP, fully offline.

A credential from the offline test issuer goes into a scripted wallet, which answers the verifier's
OpenID4VP request with direct_post. Every scenario, both formats: the verifier has to reach the verdict
the standards expect. Inji Verify 0.18.2 gets three of these wrong (FINDINGS F2, F3, F10); ours must not.
"""

import _env  # noqa: F401  (must come first)

import json
import threading
import time
import unittest

import requests
import uvicorn
from fastapi.responses import JSONResponse

import main
import presentation_flow
import verifier_service
from _env import BASE, DATA, ROOT
from verifier_client import VerifierClient
from wallet import HolderWallet


@main.app.get("/__test__/certify-did.json", include_in_schema=False)
def _certify_did():
    return JSONResponse(json.loads((ROOT / "docs" / "did.json").read_text()))


# The catch-all UI route is registered first; move it last so the test route above is reachable.
main.app.router.routes.sort(key=lambda r: getattr(r, "path", "") == "/{path:path}")

_server = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=int(BASE.rsplit(":", 1)[1]), log_level="warning"))


def setUpModule():
    threading.Thread(target=_server.run, daemon=True).start()
    for _ in range(100):
        try:
            requests.get(f"{BASE}/api/catalog", timeout=1)
            return
        except requests.ConnectionError:
            time.sleep(0.05)
    raise RuntimeError("test server didn't start")


def tearDownModule():
    _server.should_exit = True


def verifier():
    return VerifierClient(base_url=BASE + verifier_service.PREFIX, client_id=verifier_service.CLIENT_ID)


class PlaygroundVerifierScenarios(unittest.TestCase):
    """Each scenario from verify/scripts/presentation_flow.py, both formats."""

    @classmethod
    def setUpClass(cls):
        cls.wallet = HolderWallet(directory=f"{DATA}/wallet-scenarios")
        for fmt in ("ldp_vc", "vc+sd-jwt"):
            cls.wallet.receive_from_test_issuer(fmt)

    def run_scenario(self, fmt, scenario):
        result = presentation_flow.run_presentation(fmt, scenario, source="wallet", wallet=self.wallet, verifier=verifier())
        self.assertTrue(result["ok"], result.get("error"))
        return result

    def expect(self, scenario, result_status):
        for fmt in ("ldp_vc", "vc+sd-jwt"):
            with self.subTest(format=fmt):
                r = self.run_scenario(fmt, scenario)
                self.assertEqual(r["outcome"]["verdict"], "PASS", f"{fmt}: {r['verifier_result']}")
                self.assertEqual(r["verifier_result"]["status"], result_status)

    def test_honest_presentation_is_valid(self):
        self.expect("none", "VALID")

    def test_altered_claim_is_invalid(self):
        self.expect("altered", "INVALID")

    def test_wrong_credential_type_is_invalid(self):
        # Inji Verify accepts this one (FINDINGS F2).
        self.expect("wrong_type", "INVALID")

    def test_forged_issuer_is_invalid(self):
        # Inji Verify accepts this one (FINDINGS F10).
        self.expect("forged_issuer", "INVALID")

    def test_expired_credential_is_valid_but_expired(self):
        self.expect("expired", "EXPIRED")

    def test_replayed_presentation_is_refused_for_both_formats(self):
        # Inji Verify refuses the JSON-LD replay but accepts the SD-JWT one (FINDINGS F3).
        self.expect("replay", "REJECTED")


class UncheckableSignature(unittest.TestCase):
    """Found by the nightly matrix: a credential signed with a key the verifier can't find used to come
    back VALID, because "couldn't check" was treated like "checked and fine"."""

    def test_unresolvable_issuer_key_is_invalid(self):
        wallet = HolderWallet(directory=f"{DATA}/wallet-unresolvable")
        wallet.receive_from_test_issuer("ldp_vc")
        cred = wallet.credentials["ldp_vc"]["credential"]
        cred["issuer"] = "did:web:unreachable.invalid"
        cred["proof"]["verificationMethod"] = "did:web:unreachable.invalid#key-1"
        r = presentation_flow.run_presentation("ldp_vc", "none", source="wallet", wallet=wallet, verifier=verifier())
        self.assertEqual(r["verifier_result"]["status"], "INVALID", r["verifier_result"])


class ProtocolEdges(unittest.TestCase):
    def pd(self):
        return {"id": "pd-1", "input_descriptors": [{"id": "farmer", "constraints": {"fields": [{"path": ["$.type"]}]}}]}

    def open_session(self):
        r = requests.post(f"{BASE}{verifier_service.PREFIX}/vp-request",
                          json={"clientId": "playground-verifier", "nonce": "n-123", "presentationDefinition": self.pd()})
        self.assertEqual(r.status_code, 201)
        return r.json()

    def post(self, **form):
        return requests.post(f"{BASE}{verifier_service.PREFIX}/vp-submission/direct-post", data=form)

    def test_request_carries_what_a_wallet_needs(self):
        d = self.open_session()["authorizationDetails"]
        self.assertEqual(d["responseMode"], "direct_post")
        self.assertEqual(d["responseType"], "vp_token")
        self.assertEqual(d["nonce"], "n-123")
        self.assertTrue(d["responseUri"].endswith("/vp-submission/direct-post"))

    def test_request_without_input_descriptors_is_refused(self):
        r = requests.post(f"{BASE}{verifier_service.PREFIX}/vp-request", json={"presentationDefinition": {"id": "x"}})
        self.assertEqual(r.status_code, 400)

    def test_unknown_state_is_refused(self):
        r = self.post(vp_token="{}", presentation_submission="{}", state="req_nope")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["errorCode"], "INVALID_REQUEST")

    def test_presentation_for_another_nonce_is_refused(self):
        s = self.open_session()
        vp = {"type": ["VerifiablePresentation"], "proof": {"challenge": "some-other-nonce"}}
        r = self.post(vp_token=json.dumps(vp), presentation_submission="{}", state=s["requestId"])
        self.assertEqual(r.json()["errorCode"], "NONCE_VALIDATION_FAILED")

    def test_status_is_active_until_the_wallet_answers(self):
        s = self.open_session()
        verifier_service.LONG_POLL_SECONDS, saved = 0, verifier_service.LONG_POLL_SECONDS
        try:
            r = requests.get(f"{BASE}{verifier_service.PREFIX}/vp-request/{s['requestId']}/status")
        finally:
            verifier_service.LONG_POLL_SECONDS = saved
        self.assertEqual(r.json()["status"], "ACTIVE")

    def test_result_before_submission_is_refused(self):
        s = self.open_session()
        r = requests.post(f"{BASE}{verifier_service.PREFIX}/v2/vp-results/{s['transactionId']}", json={})
        self.assertEqual(r.status_code, 400)


class DigitalCredentialsApi(unittest.TestCase):
    """FR13. What a DC API wallet sends back through the browser, both protocol variants."""

    ORIGIN = "http://localhost:5050"

    @classmethod
    def setUpClass(cls):
        cls.wallet = HolderWallet(directory=f"{DATA}/wallet-dcapi")
        for fmt in ("ldp_vc", "vc+sd-jwt"):
            cls.wallet.receive_from_test_issuer(fmt)

    def answer(self, fmt, protocol, origin=None):
        req = verifier_service.create_dc_request(fmt, self.ORIGIN)
        data = next(r["data"] for r in req["requests"] if r["protocol"] == protocol)
        # what the wallet sees: no client_id over the DC API, the audience is the page's origin
        seen = {"client_id": f"origin:{origin or self.ORIGIN}", "nonce": data["nonce"],
                "presentation_definition": verifier_service._find(request_id=req["requestId"])["presentation_definition"]}
        descriptor, reasons = self.wallet.match(seen, fmt)
        self.assertFalse(reasons)
        vp = self.wallet.build_presentation(seen, fmt, descriptor)
        if protocol == "openid4vp-v1-unsigned":
            body = {"vp_token": {"farmer": [vp["vp_token"]]}}  # DCQL answer, keyed by query id
        else:
            body = {"vp_token": vp["vp_token"], "presentation_submission": vp["presentation_submission"]}
        r = requests.post(f"{BASE}{verifier_service.PREFIX}/dc-api/{req['requestId']}/response",
                          json={"protocol": protocol, "data": body})
        self.assertEqual(r.status_code, 200, r.text)
        return requests.post(f"{BASE}{verifier_service.PREFIX}/v2/vp-results/{req['transactionId']}", json={}).json()

    def test_request_offers_both_protocols(self):
        req = verifier_service.create_dc_request("vc+sd-jwt", self.ORIGIN)
        protocols = {r["protocol"]: r["data"] for r in req["requests"]}
        self.assertEqual(set(protocols), {"openid4vp-v1-unsigned", "openid4vp"})
        self.assertEqual(protocols["openid4vp-v1-unsigned"]["response_mode"], "dc_api")
        self.assertEqual(protocols["openid4vp-v1-unsigned"]["dcql_query"]["credentials"][0]["format"], "dc+sd-jwt")
        self.assertIn("presentation_definition", protocols["openid4vp"])

    def test_answers_bound_to_this_origin_are_valid(self):
        for fmt in ("ldp_vc", "vc+sd-jwt"):
            for protocol in ("openid4vp-v1-unsigned", "openid4vp"):
                with self.subTest(format=fmt, protocol=protocol):
                    self.assertTrue(self.answer(fmt, protocol)["allChecksSuccessful"])

    def test_answer_bound_to_another_site_is_invalid(self):
        for fmt in ("ldp_vc", "vc+sd-jwt"):
            with self.subTest(format=fmt):
                result = self.answer(fmt, "openid4vp-v1-unsigned", origin="https://evil.example")
                self.assertFalse(result["allChecksSuccessful"])
                self.assertIn(next(c["id"] for c in result["checks"] if c["ok"] is False), ("domain", "kb_aud"))


if __name__ == "__main__":
    unittest.main()
