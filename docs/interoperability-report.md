# Inji Interoperability Report

> Source: [successful nightly run 39871963688](https://github.com/Mushmat/inji_sandbox/actions/runs/39871963688), base commit `96d38b0892f07f9b0e972123f166476e79ec5c3f`. Original report generated 2026-10-22 23:32 UTC; artifact retrieved 2026-10-25. This is existing team CI evidence, not a new local full-stack execution.

## Evidence summary

- **74 runs: 57 PASS, 15 FAIL, 2 UNSUPPORTED; no ERROR rows.**
- All runs use the scripted Playground wallet. They exercise the preauthorized Certify, eSignet Certify and synthetic test issuer against Inji Verify and the Playground verifier.
- The 15 failures are recorded interoperability mismatches, not successful negative-path handling. A successful workflow is compatible with these findings because its default runner fails on execution errors, while `--strict` also fails on incorrect verifier answers.
- mDoc issuance is represented, but presentation is unsupported. Inji Web, physical mobile wallets and live Digital Credentials API consent are not covered by these runs.
- Configured module versions listed below do not imply every listed module was exercised.
- This report covers the submitted local stack with Collab eSignet authentication; it is not a full matrix against all public Collab modules.

[Current verification evidence](evidence/verification.json) records local checks on the same application commit. [Submission checklist](submission-checklist.md) records manual and unresolved acceptance items.

## Local verification — 2026-10-25

The unchanged application was run with isolated temporary history on port 5051. The test issuer issued credentials directly to the scripted wallet; presentation used real HTTP against the Playground verifier and the running Inji Verify 0.18.2 container. This does not exercise OpenID4VCI issuance or Inji Web.

Each path ran honest, altered-claim, replay, wrong-type, forged-issuer and expired-credential scenarios:

| Verifier | Format | Runs | PASS | FAIL | ERROR |
|---|---|---|---|---|---|
| Playground verifier | JSON-LD | 6 | 6 | 0 | 0 |
| Playground verifier | SD-JWT | 6 | 5 | 1 | 0 |
| Inji Verify | JSON-LD | 6 | 4 | 2 | 0 |
| Inji Verify | SD-JWT | 6 | 3 | 3 | 0 |
| **Total** | | **24** | **18** | **6** | **0** |

All four honest paths passed. Inji Verify accepted wrong-type and forged-issuer credentials in both formats, and a replayed SD-JWT. These five failures match the known scenario gaps, although the independent SD-JWT issuer-key check could not complete without Certify.

The sixth failure is in the Playground verifier: a forged SD-JWT returned `VALID` when Certify's DID endpoint was unavailable. The `issuer_signature` check passed against the submitted self-signed certificate, but `issuer_key_binding` returned unknown. `playground/bff/verifier_service.py` treats unknown issuer signatures as failures, but does not apply the same rule to unknown issuer-key binding. A controlled comparison confirmed that the same unrelated key is rejected when the expected issuer keys are supplied. The offline suite supplies a reachable DID fixture, so its passing result does not cover this outage condition.

The API compatibility response, invalid-combination rejection, saved history, wallet summaries, Markdown export and OpenAPI endpoint passed smoke checks. In the browser, a separate honest JSON-LD run against Inji Verify passed; the protocol inspector, sequence diagram, report totals and failure filter were checked. That additional run is separate from the 24-case table.

Full-stack startup was attempted with `python3 integration/stack.py up` and stopped because `wallet/docker-compose/.env` was missing. The shared issuer signing keystore and database seed were also absent. Certify, Mimoto and Inji Web were therefore unavailable for fresh acceptance testing. Follow the [private-file setup](../README.md#run-it), then repeat real issuance, wallet download and consent before claiming full-stack acceptance.

To repeat the 24 scenarios without changing issuer data, start the BFF with temporary `PLAYGROUND_DATA_DIR`, choose the test issuer and scripted wallet, and run each of the six scenarios for both JSON-LD and SD-JWT against each verifier. Keep Certify unavailable to reproduce the unresolved issuer-key condition. Check the API's run history and export the resulting report. This is a limited smoke matrix; the full 74-run matrix requires the complete configured stack.

## Archived nightly report

The following is the original downloaded nightly report, with its results retained.

Generated 2026-10-22 23:32 UTC from 74 runs.

Module versions: Inji Certify 0.14.0, Inji Verify 0.18.2, Inji Web 0.17.0, Mimoto 0.22.0

## Matrix (latest honest run per combination)

| Issuer | Wallet | Verifier | Format | Proof type | Result | Verdict |
|---|---|---|---|---|---|---|
| Test issuer | Playground wallet | Playground verifier | SD-JWT | SD-JWT (EdDSA) | VALID | PASS |
| Test issuer | Playground wallet | Playground verifier | JSON-LD | Ed25519Signature2020 | VALID | PASS |
| Test issuer | Playground wallet | Inji Verify | SD-JWT | SD-JWT (EdDSA) | VALID | PASS |
| Test issuer | Playground wallet | Inji Verify | JSON-LD | Ed25519Signature2020 | VALID | PASS |
| Inji Certify · eSignet login | Playground wallet | Playground verifier | mDoc | COSE_Sign1 (mso_mdoc) | UNSUPPORTED | UNSUPPORTED |
| Inji Certify · eSignet login | Playground wallet | Playground verifier | SD-JWT | SD-JWT (EdDSA) | VALID | PASS |
| Inji Certify · eSignet login | Playground wallet | Playground verifier | JSON-LD | Ed25519Signature2020 | VALID | PASS |
| Inji Certify · eSignet login | Playground wallet | Inji Verify | mDoc | COSE_Sign1 (mso_mdoc) | UNSUPPORTED | UNSUPPORTED |
| Inji Certify · eSignet login | Playground wallet | Inji Verify | SD-JWT | SD-JWT (EdDSA) | VALID | PASS |
| Inji Certify · eSignet login | Playground wallet | Inji Verify | JSON-LD | Ed25519Signature2020 | VALID | PASS |
| Inji Certify · pre-authorized | Playground wallet | Playground verifier | SD-JWT | SD-JWT (EdDSA) | VALID | PASS |
| Inji Certify · pre-authorized | Playground wallet | Playground verifier | JSON-LD | Ed25519Signature2020 | VALID | PASS |
| Inji Certify · pre-authorized | Playground wallet | Inji Verify | SD-JWT | SD-JWT (EdDSA) | VALID | PASS |
| Inji Certify · pre-authorized | Playground wallet | Inji Verify | JSON-LD | Ed25519Signature2020 | VALID | PASS |

## Flow health

Automated runs only for the times; Inji Web runs wait on a person.

| Issuer | Wallet | Verifier | Format | Runs | Completed | Correct verdict | Median | p95 |
|---|---|---|---|---|---|---|---|---|
| Test issuer | Playground wallet | Playground verifier | SD-JWT | 6 | 100% | 100% | 0.0 s | 0.1 s |
| Test issuer | Playground wallet | Playground verifier | JSON-LD | 6 | 100% | 100% | 0.0 s | 0.0 s |
| Test issuer | Playground wallet | Inji Verify | SD-JWT | 6 | 100% | 50% | 0.0 s | 0.1 s |
| Test issuer | Playground wallet | Inji Verify | JSON-LD | 6 | 100% | 67% | 0.4 s | 0.6 s |
| Inji Certify · eSignet login | Playground wallet | Playground verifier | SD-JWT | 6 | 100% | 100% | 3.2 s | 6.2 s |
| Inji Certify · eSignet login | Playground wallet | Playground verifier | JSON-LD | 6 | 100% | 100% | 3.7 s | 6.6 s |
| Inji Certify · eSignet login | Playground wallet | Inji Verify | SD-JWT | 6 | 100% | 50% | 3.6 s | 6.5 s |
| Inji Certify · eSignet login | Playground wallet | Inji Verify | JSON-LD | 6 | 100% | 67% | 4.2 s | 9.3 s |
| Inji Certify · pre-authorized | Playground wallet | Playground verifier | SD-JWT | 6 | 100% | 100% | 0.6 s | 0.7 s |
| Inji Certify · pre-authorized | Playground wallet | Playground verifier | JSON-LD | 6 | 100% | 100% | 1.0 s | 1.2 s |
| Inji Certify · pre-authorized | Playground wallet | Inji Verify | SD-JWT | 6 | 100% | 50% | 0.9 s | 1.0 s |
| Inji Certify · pre-authorized | Playground wallet | Inji Verify | JSON-LD | 6 | 100% | 67% | 1.7 s | 4.1 s |
| Inji Certify · eSignet login | Playground wallet | Playground verifier | mDoc | 1 | 100% | 0% | 3.1 s | 3.1 s |
| Inji Certify · eSignet login | Playground wallet | Inji Verify | mDoc | 1 | 100% | 0% | 3.3 s | 3.3 s |

## Every run

| When (UTC) | Issuer | Wallet | Verifier | Format | Scenario | Expected | Result | Verdict | Detail |
|---|---|---|---|---|---|---|---|---|---|
| 2026-10-22 23:32:31 | Test issuer | Playground wallet | Playground verifier | SD-JWT | Expired credential | EXPIRED | EXPIRED | PASS |  |
| 2026-10-22 23:32:30 | Test issuer | Playground wallet | Playground verifier | SD-JWT | Forged issuer | INVALID | INVALID | PASS |  |
| 2026-10-22 23:32:29 | Test issuer | Playground wallet | Playground verifier | SD-JWT | Wrong credential type | INVALID | INVALID | PASS |  |
| 2026-10-22 23:32:28 | Test issuer | Playground wallet | Playground verifier | SD-JWT | Replayed presentation | INVALID | REJECTED | PASS |  |
| 2026-10-22 23:32:27 | Test issuer | Playground wallet | Playground verifier | SD-JWT | Altered claim | INVALID | INVALID | PASS |  |
| 2026-10-22 23:32:26 | Test issuer | Playground wallet | Playground verifier | SD-JWT | Honest | VALID | VALID | PASS |  |
| 2026-10-22 23:32:25 | Test issuer | Playground wallet | Playground verifier | JSON-LD | Expired credential | EXPIRED | EXPIRED | PASS |  |
| 2026-10-22 23:32:24 | Test issuer | Playground wallet | Playground verifier | JSON-LD | Forged issuer | INVALID | INVALID | PASS |  |
| 2026-10-22 23:32:23 | Test issuer | Playground wallet | Playground verifier | JSON-LD | Wrong credential type | INVALID | INVALID | PASS |  |
| 2026-10-22 23:32:22 | Test issuer | Playground wallet | Playground verifier | JSON-LD | Replayed presentation | INVALID | REJECTED | PASS |  |
| 2026-10-22 23:32:21 | Test issuer | Playground wallet | Playground verifier | JSON-LD | Altered claim | INVALID | INVALID | PASS |  |
| 2026-10-22 23:32:20 | Test issuer | Playground wallet | Playground verifier | JSON-LD | Honest | VALID | VALID | PASS |  |
| 2026-10-22 23:32:19 | Test issuer | Playground wallet | Inji Verify | SD-JWT | Expired credential | EXPIRED | EXPIRED | PASS |  |
| 2026-10-22 23:32:18 | Test issuer | Playground wallet | Inji Verify | SD-JWT | Forged issuer | INVALID | VALID | FAIL | Inji Verify accepted the presentation although the playground's checks failed: Signing key belongs to the issuer |
| 2026-10-22 23:32:17 | Test issuer | Playground wallet | Inji Verify | SD-JWT | Wrong credential type | INVALID | VALID | FAIL | Inji Verify accepted the presentation although the playground's checks failed: Credential meets the presentation_definition constraints |
| 2026-10-22 23:32:16 | Test issuer | Playground wallet | Inji Verify | SD-JWT | Replayed presentation | INVALID | VALID | FAIL | Inji Verify accepted the presentation although the playground's checks failed: KB-JWT nonce is this session's nonce |
| 2026-10-22 23:32:15 | Test issuer | Playground wallet | Inji Verify | SD-JWT | Altered claim | INVALID | INVALID | PASS |  |
| 2026-10-22 23:32:14 | Test issuer | Playground wallet | Inji Verify | SD-JWT | Honest | VALID | VALID | PASS |  |
| 2026-10-22 23:32:13 | Test issuer | Playground wallet | Inji Verify | JSON-LD | Expired credential | EXPIRED | EXPIRED | PASS |  |
| 2026-10-22 23:32:12 | Test issuer | Playground wallet | Inji Verify | JSON-LD | Forged issuer | INVALID | VALID | FAIL | Inji Verify accepted the presentation although the playground's checks failed: Signing key belongs to the issuer |
| 2026-10-22 23:32:10 | Test issuer | Playground wallet | Inji Verify | JSON-LD | Wrong credential type | INVALID | VALID | FAIL | Inji Verify accepted the presentation although the playground's checks failed: Credential meets the presentation_definition constraints |
| 2026-10-22 23:32:09 | Test issuer | Playground wallet | Inji Verify | JSON-LD | Replayed presentation | INVALID | REJECTED | PASS |  |
| 2026-10-22 23:32:08 | Test issuer | Playground wallet | Inji Verify | JSON-LD | Altered claim | INVALID | INVALID | PASS |  |
| 2026-10-22 23:32:07 | Test issuer | Playground wallet | Inji Verify | JSON-LD | Honest | VALID | VALID | PASS |  |
| 2026-10-22 23:32:03 | Inji Certify · eSignet login | Playground wallet | Playground verifier | mDoc | Honest | VALID | UNSUPPORTED | UNSUPPORTED | Playground wallet can't present mDoc. |
| 2026-10-22 23:31:59 | Inji Certify · eSignet login | Playground wallet | Playground verifier | SD-JWT | Expired credential | EXPIRED | EXPIRED | PASS |  |
| 2026-10-22 23:31:52 | Inji Certify · eSignet login | Playground wallet | Playground verifier | SD-JWT | Forged issuer | INVALID | INVALID | PASS |  |
| 2026-10-22 23:31:48 | Inji Certify · eSignet login | Playground wallet | Playground verifier | SD-JWT | Wrong credential type | INVALID | INVALID | PASS |  |
| 2026-10-22 23:31:44 | Inji Certify · eSignet login | Playground wallet | Playground verifier | SD-JWT | Replayed presentation | INVALID | REJECTED | PASS |  |
| 2026-10-22 23:31:40 | Inji Certify · eSignet login | Playground wallet | Playground verifier | SD-JWT | Altered claim | INVALID | INVALID | PASS |  |
| 2026-10-22 23:31:33 | Inji Certify · eSignet login | Playground wallet | Playground verifier | SD-JWT | Honest | VALID | VALID | PASS |  |
| 2026-10-22 23:31:29 | Inji Certify · eSignet login | Playground wallet | Playground verifier | JSON-LD | Expired credential | EXPIRED | EXPIRED | PASS |  |
| 2026-10-22 23:31:25 | Inji Certify · eSignet login | Playground wallet | Playground verifier | JSON-LD | Forged issuer | INVALID | INVALID | PASS |  |
| 2026-10-22 23:31:21 | Inji Certify · eSignet login | Playground wallet | Playground verifier | JSON-LD | Wrong credential type | INVALID | INVALID | PASS |  |
| 2026-10-22 23:31:14 | Inji Certify · eSignet login | Playground wallet | Playground verifier | JSON-LD | Replayed presentation | INVALID | REJECTED | PASS |  |
| 2026-10-22 23:31:10 | Inji Certify · eSignet login | Playground wallet | Playground verifier | JSON-LD | Altered claim | INVALID | INVALID | PASS |  |
| 2026-10-22 23:31:06 | Inji Certify · eSignet login | Playground wallet | Playground verifier | JSON-LD | Honest | VALID | VALID | PASS |  |
| 2026-10-22 23:31:02 | Inji Certify · eSignet login | Playground wallet | Inji Verify | mDoc | Honest | VALID | UNSUPPORTED | UNSUPPORTED | Playground wallet can't present mDoc. |
| 2026-10-22 23:30:55 | Inji Certify · eSignet login | Playground wallet | Inji Verify | SD-JWT | Expired credential | EXPIRED | EXPIRED | PASS |  |
| 2026-10-22 23:30:51 | Inji Certify · eSignet login | Playground wallet | Inji Verify | SD-JWT | Forged issuer | INVALID | VALID | FAIL | Inji Verify accepted the presentation although the playground's checks failed: Signing key belongs to the issuer |
| 2026-10-22 23:30:47 | Inji Certify · eSignet login | Playground wallet | Inji Verify | SD-JWT | Wrong credential type | INVALID | VALID | FAIL | Inji Verify accepted the presentation although the playground's checks failed: Credential meets the presentation_definition constraints |
| 2026-10-22 23:30:43 | Inji Certify · eSignet login | Playground wallet | Inji Verify | SD-JWT | Replayed presentation | INVALID | VALID | FAIL | Inji Verify accepted the presentation although the playground's checks failed: KB-JWT nonce is this session's nonce |
| 2026-10-22 23:30:36 | Inji Certify · eSignet login | Playground wallet | Inji Verify | SD-JWT | Altered claim | INVALID | INVALID | PASS |  |
| 2026-10-22 23:30:32 | Inji Certify · eSignet login | Playground wallet | Inji Verify | SD-JWT | Honest | VALID | VALID | PASS |  |
| 2026-10-22 23:30:28 | Inji Certify · eSignet login | Playground wallet | Inji Verify | JSON-LD | Expired credential | EXPIRED | EXPIRED | PASS |  |
| 2026-10-22 23:30:23 | Inji Certify · eSignet login | Playground wallet | Inji Verify | JSON-LD | Forged issuer | INVALID | VALID | FAIL | Inji Verify accepted the presentation although the playground's checks failed: Signing key belongs to the issuer |
| 2026-10-22 23:30:15 | Inji Certify · eSignet login | Playground wallet | Inji Verify | JSON-LD | Wrong credential type | INVALID | VALID | FAIL | Inji Verify accepted the presentation although the playground's checks failed: Credential meets the presentation_definition constraints |
| 2026-10-22 23:30:10 | Inji Certify · eSignet login | Playground wallet | Inji Verify | JSON-LD | Replayed presentation | INVALID | REJECTED | PASS |  |
| 2026-10-22 23:30:06 | Inji Certify · eSignet login | Playground wallet | Inji Verify | JSON-LD | Altered claim | INVALID | INVALID | PASS |  |
| 2026-10-22 23:29:56 | Inji Certify · eSignet login | Playground wallet | Inji Verify | JSON-LD | Honest | VALID | VALID | PASS |  |
| 2026-10-22 23:29:55 | Inji Certify · pre-authorized | Playground wallet | Playground verifier | SD-JWT | Expired credential | EXPIRED | EXPIRED | PASS |  |
| 2026-10-22 23:29:54 | Inji Certify · pre-authorized | Playground wallet | Playground verifier | SD-JWT | Forged issuer | INVALID | INVALID | PASS |  |
| 2026-10-22 23:29:53 | Inji Certify · pre-authorized | Playground wallet | Playground verifier | SD-JWT | Wrong credential type | INVALID | INVALID | PASS |  |
| 2026-10-22 23:29:52 | Inji Certify · pre-authorized | Playground wallet | Playground verifier | SD-JWT | Replayed presentation | INVALID | REJECTED | PASS |  |
| 2026-10-22 23:29:51 | Inji Certify · pre-authorized | Playground wallet | Playground verifier | SD-JWT | Altered claim | INVALID | INVALID | PASS |  |
| 2026-10-22 23:29:50 | Inji Certify · pre-authorized | Playground wallet | Playground verifier | SD-JWT | Honest | VALID | VALID | PASS |  |
| 2026-10-22 23:29:49 | Inji Certify · pre-authorized | Playground wallet | Playground verifier | JSON-LD | Expired credential | EXPIRED | EXPIRED | PASS |  |
| 2026-10-22 23:29:48 | Inji Certify · pre-authorized | Playground wallet | Playground verifier | JSON-LD | Forged issuer | INVALID | INVALID | PASS |  |
| 2026-10-22 23:29:47 | Inji Certify · pre-authorized | Playground wallet | Playground verifier | JSON-LD | Wrong credential type | INVALID | INVALID | PASS |  |
| 2026-10-22 23:29:45 | Inji Certify · pre-authorized | Playground wallet | Playground verifier | JSON-LD | Replayed presentation | INVALID | REJECTED | PASS |  |
| 2026-10-22 23:29:43 | Inji Certify · pre-authorized | Playground wallet | Playground verifier | JSON-LD | Altered claim | INVALID | INVALID | PASS |  |
| 2026-10-22 23:29:41 | Inji Certify · pre-authorized | Playground wallet | Playground verifier | JSON-LD | Honest | VALID | VALID | PASS |  |
| 2026-10-22 23:29:40 | Inji Certify · pre-authorized | Playground wallet | Inji Verify | SD-JWT | Expired credential | EXPIRED | EXPIRED | PASS |  |
| 2026-10-22 23:29:39 | Inji Certify · pre-authorized | Playground wallet | Inji Verify | SD-JWT | Forged issuer | INVALID | VALID | FAIL | Inji Verify accepted the presentation although the playground's checks failed: Signing key belongs to the issuer |
| 2026-10-22 23:29:38 | Inji Certify · pre-authorized | Playground wallet | Inji Verify | SD-JWT | Wrong credential type | INVALID | VALID | FAIL | Inji Verify accepted the presentation although the playground's checks failed: Credential meets the presentation_definition constraints |
| 2026-10-22 23:29:37 | Inji Certify · pre-authorized | Playground wallet | Inji Verify | SD-JWT | Replayed presentation | INVALID | VALID | FAIL | Inji Verify accepted the presentation although the playground's checks failed: KB-JWT nonce is this session's nonce |
| 2026-10-22 23:29:36 | Inji Certify · pre-authorized | Playground wallet | Inji Verify | SD-JWT | Altered claim | INVALID | INVALID | PASS |  |
| 2026-10-22 23:29:35 | Inji Certify · pre-authorized | Playground wallet | Inji Verify | SD-JWT | Honest | VALID | VALID | PASS |  |
| 2026-10-22 23:29:33 | Inji Certify · pre-authorized | Playground wallet | Inji Verify | JSON-LD | Expired credential | EXPIRED | EXPIRED | PASS |  |
| 2026-10-22 23:29:31 | Inji Certify · pre-authorized | Playground wallet | Inji Verify | JSON-LD | Forged issuer | INVALID | VALID | FAIL | Inji Verify accepted the presentation although the playground's checks failed: Signing key belongs to the issuer |
| 2026-10-22 23:29:29 | Inji Certify · pre-authorized | Playground wallet | Inji Verify | JSON-LD | Wrong credential type | INVALID | VALID | FAIL | Inji Verify accepted the presentation although the playground's checks failed: Credential meets the presentation_definition constraints |
| 2026-10-22 23:29:27 | Inji Certify · pre-authorized | Playground wallet | Inji Verify | JSON-LD | Replayed presentation | INVALID | REJECTED | PASS |  |
| 2026-10-22 23:29:25 | Inji Certify · pre-authorized | Playground wallet | Inji Verify | JSON-LD | Altered claim | INVALID | INVALID | PASS |  |
| 2026-10-22 23:29:20 | Inji Certify · pre-authorized | Playground wallet | Inji Verify | JSON-LD | Honest | VALID | VALID | PASS |  |

Finding IDs (F*, W*, M*) refer to verify/docs/FINDINGS.md and wallet/README.md.
