# Inji Interoperability Report

Generated 2026-09-29 18:47 UTC from 14 runs.

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
| Test issuer | Playground wallet | Playground verifier | SD-JWT | 1 | 100% | 100% | 0.0 s | 0.0 s |
| Test issuer | Playground wallet | Playground verifier | JSON-LD | 1 | 100% | 100% | 0.1 s | 0.1 s |
| Test issuer | Playground wallet | Inji Verify | SD-JWT | 1 | 100% | 100% | 0.4 s | 0.4 s |
| Test issuer | Playground wallet | Inji Verify | JSON-LD | 1 | 100% | 100% | 3.2 s | 3.2 s |
| Inji Certify · eSignet login | Playground wallet | Playground verifier | mDoc | 1 | 100% | 0% | 6.2 s | 6.2 s |
| Inji Certify · eSignet login | Playground wallet | Playground verifier | SD-JWT | 1 | 100% | 100% | 3.7 s | 3.7 s |
| Inji Certify · eSignet login | Playground wallet | Playground verifier | JSON-LD | 1 | 100% | 100% | 14.4 s | 14.4 s |
| Inji Certify · eSignet login | Playground wallet | Inji Verify | mDoc | 1 | 100% | 0% | 5.6 s | 5.6 s |
| Inji Certify · eSignet login | Playground wallet | Inji Verify | SD-JWT | 1 | 100% | 100% | 4.8 s | 4.8 s |
| Inji Certify · eSignet login | Playground wallet | Inji Verify | JSON-LD | 1 | 100% | 100% | 14.1 s | 14.1 s |
| Inji Certify · pre-authorized | Playground wallet | Playground verifier | SD-JWT | 1 | 100% | 100% | 1.3 s | 1.3 s |
| Inji Certify · pre-authorized | Playground wallet | Playground verifier | JSON-LD | 1 | 100% | 100% | 2.2 s | 2.2 s |
| Inji Certify · pre-authorized | Playground wallet | Inji Verify | SD-JWT | 1 | 100% | 100% | 1.8 s | 1.8 s |
| Inji Certify · pre-authorized | Playground wallet | Inji Verify | JSON-LD | 1 | 100% | 100% | 6.5 s | 6.5 s |

## Every run

| When (UTC) | Issuer | Wallet | Verifier | Format | Scenario | Expected | Result | Verdict | Detail |
|---|---|---|---|---|---|---|---|---|---|
| 2026-09-29 18:47:57 | Test issuer | Playground wallet | Playground verifier | SD-JWT | Honest | VALID | VALID | PASS |  |
| 2026-09-29 18:47:56 | Test issuer | Playground wallet | Playground verifier | JSON-LD | Honest | VALID | VALID | PASS |  |
| 2026-09-29 18:47:55 | Test issuer | Playground wallet | Inji Verify | SD-JWT | Honest | VALID | VALID | PASS |  |
| 2026-09-29 18:47:51 | Test issuer | Playground wallet | Inji Verify | JSON-LD | Honest | VALID | VALID | PASS |  |
| 2026-09-29 18:47:44 | Inji Certify · eSignet login | Playground wallet | Playground verifier | mDoc | Honest | VALID | UNSUPPORTED | UNSUPPORTED | Playground wallet can't present mDoc. |
| 2026-09-29 18:47:40 | Inji Certify · eSignet login | Playground wallet | Playground verifier | SD-JWT | Honest | VALID | VALID | PASS |  |
| 2026-09-29 18:47:25 | Inji Certify · eSignet login | Playground wallet | Playground verifier | JSON-LD | Honest | VALID | VALID | PASS |  |
| 2026-09-29 18:47:19 | Inji Certify · eSignet login | Playground wallet | Inji Verify | mDoc | Honest | VALID | UNSUPPORTED | UNSUPPORTED | Playground wallet can't present mDoc. |
| 2026-09-29 18:47:14 | Inji Certify · eSignet login | Playground wallet | Inji Verify | SD-JWT | Honest | VALID | VALID | PASS |  |
| 2026-09-29 18:46:59 | Inji Certify · eSignet login | Playground wallet | Inji Verify | JSON-LD | Honest | VALID | VALID | PASS |  |
| 2026-09-29 18:46:57 | Inji Certify · pre-authorized | Playground wallet | Playground verifier | SD-JWT | Honest | VALID | VALID | PASS |  |
| 2026-09-29 18:46:54 | Inji Certify · pre-authorized | Playground wallet | Playground verifier | JSON-LD | Honest | VALID | VALID | PASS |  |
| 2026-09-29 18:46:52 | Inji Certify · pre-authorized | Playground wallet | Inji Verify | SD-JWT | Honest | VALID | VALID | PASS |  |
| 2026-09-29 18:46:45 | Inji Certify · pre-authorized | Playground wallet | Inji Verify | JSON-LD | Honest | VALID | VALID | PASS |  |

Finding IDs (F*, W*, M*) refer to verify/docs/FINDINGS.md and wallet/README.md.
