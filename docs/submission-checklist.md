# Submission acceptance checklist

Reviewed 2026-10-25 against application commit `96d38b0`.

## Original role split

The team's September 18 baseline, Roadmap page 1, suggests four roles:

| Role | Ownership |
|---|---|
| Issuer and backend | Certify and BFF; issuer setup, issuance and formats |
| Wallet | Inji Wallet/Web; wallet setup, issuance and presentation |
| Verifier and protocol | Verify, presentation and inspector |
| Playground UI and Docs Lead | FR2 selector, FR7 reporting, README/architecture/API documentation |

The plan labels this role split a suggestion.

## Functional acceptance

"Implemented" describes source capability; a test or recorded run establishes only the coverage it actually exercises.

| FR | Current evidence and acceptance limit | Next owner/action |
|---|---|---|
| FR1 connected stack | Docker integration exists; previous real Inji Web results are recorded in `verify/docs/FINDINGS.md`. The nightly matrix uses a scripted holder. | Component owners: repeat the real-wallet flow on the demo machine. |
| FR2 selector | Existing three-column UI; default holder is the non-Inji scripted wallet despite the plan's all-Inji initial-selection wording. | UI owner: confirm or change that default. |
| FR3 issuance | Nightly report includes real local Certify preauthorized/eSignet issuance. Mimoto's internal issuance exchanges are not captured. | Issuer/wallet owners: demonstrate the actual wallet download. |
| FR4 presentation | Nightly positive, negative and expiry cases; previous manual JSON-LD wallet evidence exists. | Wallet/verifier owners: repeat the live consent flow. |
| FR5 inspector | Scripted payload capture exists; real-wallet internal issuance and submitted VP are incomplete. | Protocol/wallet owners: resolve capture or declare the limitation. |
| FR6 two formats | JSON-LD and SD-JWT work with the scripted holder. Pinned Inji Web receives SD-JWT but does not present it. | Wallet owner: resolve or document the all-Inji SD-JWT gap. |
| FR7 reporting | Full 74-run nightly report is included here with provenance and failures preserved. Export API and dashboard already exist. | Docs owner: refresh the artifact if the submitted code changes. |
| FR8 non-Inji mock | Test issuer, scripted holder and independent verifier exist. Local smoke testing found forged SD-JWT acceptance when issuer-key lookup is unavailable. | Verifier owner: reject unresolved mandatory issuer-key checks; successful offline scenarios do not certify general standards compliance. |
| FR9 mDoc | Mock issuance exists; presentation is reported UNSUPPORTED. The plan asks for a third format via Certify mock support, not proof of a completed mDoc VP path. | Component owners: retain the exact issuance-only scope. |
| FR10 sequence diagram | Existing live Mermaid view and helper tests. | Demo: show it updating during a real flow. |
| FR11 replay/tamper | Nightly scenarios run; upstream acceptance of invalid input produces FAIL rows. | Verifier owner: distinguish findings from correctly rejected cases. |
| FR12 history | Existing SQLite-backed dashboard and filters. | Demo: show history/filter/export behavior. |
| FR13 same-device | Deep-link and DC API entry points exist; device-based DC API acceptance was not established here. | Wallet owner: demonstrate a configured device, or state that limitation. |
| FR14 nightly suite | Existing scheduled local-stack workflow, Collab eSignet login and endpoint probes. It is not a full Collab-module matrix as the baseline specifies. | CI/protocol owners: decide and document the coverage difference. |
| FR15 upstream reporting | Findings are written up; issue/disclosure receipt links are not recorded in the project. | Team: confirm existing tickets and private-disclosure receipt before marking complete. |
| FR16 telemetry | Existing rates and latency dashboard; nightly report contains recorded flow timings. | Demo: explain completion rate versus correct-verdict rate. |
| FR17 one-command setup | Existing integration script; startup requires private signing and Google OAuth configuration. | Follow the README's private-file setup, then verify fresh startup. |

## Documentation deliverables

- [x] Main README links to the submission documents.
- [x] [Architecture and sequence diagrams](architecture.md) reflect the implementation.
- [x] [Playground API documentation](API_DOCUMENTATION.md); existing issuer/verifier API docs are linked.
- [x] [Full interoperability report](interoperability-report.md), with source run, commit, coverage and failures.
- [x] [Verification record](evidence/verification.json) separates current offline checks from historical live evidence.
- [x] [Four-minute demo script](demo-script.md).
- [ ] Record the actual 3–5 minute video and add its final URL.
- [ ] Confirm the submission deadline and upload requirements with the organisers.
- [ ] Verify that the final submitted application code matches the tested commit; rerun affected checks after code changes.

## Test data and privacy

Test fixtures exist under `certify/docker-compose/config/farmer_identity_data.csv`, `verify/scripts/test_issuer.py` and `verify/scripts/tests/fixtures/`. The CSV contains embedded sample images. Their synthetic/stand-in provenance has not been established; the issuer owner must confirm or replace them before submission.

Use mock identities only. Raw scripted traces may contain tokens; publish the summary report rather than raw token-bearing exchanges. Private keys, OAuth configuration and seed files are setup prerequisites, not submission attachments. The report here contains summary rows rather than credential bodies or bearer tokens.

## Reproduce the checks

For the full Docker stack, follow [README: private files and startup](../README.md#run-it). Obtain the shared issuer keystore and matching database seed from the issuer owner; obtain the wallet OAuth configuration from its owner or configure a Google OAuth client using [wallet setup](../wallet/README.md). Keep these files out of Git. A fresh clone alone cannot reproduce the real-wallet flow without these prerequisites and an authorised Google test user.

For the automated checks, use Python 3.12 and Node.js 22, matching the CI workflow. From the repository root on macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r playground/bff/requirements.txt
python -m unittest discover -s playground/bff/tests -p 'test_*.py' -v
cd verify/scripts
ALLOW_REMOTE_CONTEXTS=0 python -m unittest discover -s tests -v
cd ../../playground/web
npm ci
npm test
npm run build
```

These checks cover the scripted protocol harness and UI. They do not replace live Certify issuance, Inji Web download/consent or physical-device testing. The presentation suite skips live cases when their services are unavailable. The verification record identifies the actual local runtime and results; CI runtime versions above are the reproduction target.

## CI and evidence interpretation

The existing push/PR workflow runs backend tests, the presentation suite, frontend tests and a frontend build. The nightly workflow is scheduled at 20:30 UTC (02:00 IST the following day), restores repository signing secrets, starts local services and runs the full automated matrix.

Run `python playground/run_matrix.py --full --out docs/interoperability-report.md` against a ready full stack to generate a replacement report. Preserve provenance and coverage notes when updating it. The current runner returns failure on execution ERRORs; `--strict` also treats standards FAILs as failure. Therefore the source nightly's successful conclusion does not erase its 15 failed interoperability cases.

No live wallet/device demonstration, missing private setup file, video, upstream fix or contributor commit should be marked complete from offline tests alone. The plan asks for real history from all four teammates; Git author identities alone do not prove that requirement.
