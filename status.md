# Status — Inji Interoperability Playground

Last reviewed: 2026-10-25 (documentation and evidence; application code unchanged at `96d38b0`)

## Summary

The three pipelines (Certify, the wallet, Present & Verify) are integrated and run
together from one command, with the Playground on top: one page that runs issue →
hold → present → verify across supported issuer, wallet and verifier combinations,
shows recorded protocol messages, and compares results with the expected behavior.
The implemented features include prior manual Inji Web results, but real-wallet
payload capture and all-Inji SD-JWT presentation remain incomplete. The current
[submission checklist](docs/submission-checklist.md) distinguishes source capability,
recorded evidence and outstanding acceptance work.

How to run it, on macOS or Windows: [README.md](README.md#run-it).

## What works

**One stack, one command.** `python integration/stack.py up` starts Certify (two
instances, same keys and `did:web`), Inji Verify, Mimoto + Inji Web, two https tunnels
and the Playground, all in Docker. `down` stops it and keeps the data.

**Issuers.** Inji Certify with the pre-authorized code flow (Certify writes the
credential offer itself and takes the person's details with each offer), Inji Certify
with an eSignet login (what Inji Web uses), and a non-Inji `did:key` test issuer.
JSON-LD, SD-JWT and mDoc.

**Wallets.** A scripted Playground wallet (can misbehave on purpose for tamper tests),
Inji Web (driven by a person, guided by the page), and a browser wallet through the
Digital Credentials API.

**Verifiers.** Inji Verify, and our own Playground verifier: a non-Inji OpenID4VP
relying party written from the specs.

**The Playground page.** Issuer → Wallet → Verifier selector, format and tamper
scenarios, a live protocol inspector with every request and response (JWTs decodable
in place), a live sequence diagram, an editable credential subject (with camera or
uploaded photo and field validation), a report with a compatibility matrix, flow
health (success rates and latency), filterable history and markdown export, and a
test matrix that runs every automated combination.

**Tests.** The documentation review reran 33 backend tests and 10 frontend tests.
The presentation suite passed 31 offline checks and skipped four live checks;
the 14 live Certify tests were not rerun. The frontend production build passed.
Exact commands and the separate nightly provenance are in the
[verification record](docs/evidence/verification.json).

Fresh local smoke testing exercised 24 scripted issue → hold → present → verify
flows: 18 PASS and 6 FAIL, with no execution errors. A separate browser-triggered
honest JSON-LD flow against Inji Verify passed; the inspector, sequence diagram,
report and failure filter were checked. The full real-wallet startup stopped at
the missing Google OAuth configuration; the shared issuer keystore and seed are
also required. See the [local results](docs/interoperability-report.md#local-verification--2026-10-25).

## What we found

Inji Verify 0.18.2 accepts a wrong credential type (F2), an SD-JWT replayed from another
session (F3), and a credential signed by someone else's key that names Certify as the
issuer (F10). The Playground verifier detects these in the configured nightly
stack, but local testing with Certify unavailable exposed forged SD-JWT acceptance
when issuer-key lookup remains unresolved. This validation gap remains open. The full list, with how to
reproduce each, is in [verify/docs/FINDINGS.md](verify/docs/FINDINGS.md), the "Known
gaps" in [wallet/README.md](wallet/README.md) and "What we found" in
[certify/README.md](certify/README.md).

## Fixed since the last update

- **Nightly matrix failures.** The key seed was never loaded in CI (Docker Compose skips
  the override file once `-f` is used), so Certify signed with keys that didn't match the
  published DID; the pre-authorized Certify rejected tokens carrying MOSIP's 92 KB sample
  photo (header limit raised); and the Playground verifier accepted a signature it
  couldn't check (it now refuses). The workflow now stops early if the keys don't match.
- **The same Compose rule in `stack.py`**: a teammate's shared signing key would have been
  ignored. `stack.py` now loads it.
- **Fresh Windows machines**: the wallet keystore is now generated inside Docker, so the
  host needs no Python libraries.
- Saving the person no longer restarts Certify; the eSignet Certify reloads on request.
- Runs interrupted by a restart close themselves; runs wait for the services they need.

## Known limits

- Inji Web and Inji Verify can't take mDoc over OpenID4VP, and Inji Web can't present
  SD-JWT. These are MOSIP-side; runs record them as UNSUPPORTED or a known limit.
- The Inji Wallet phone app and the Digital Credentials API need a wallet configured
  for our issuer and verifiers. Our side is built and tested; a live run needs that
  wallet. Not required: the Inji Web deep link covers FR4 and FR13.
- Each machine running Certify needs the shared signing key, or its credentials won't
  verify against the published DID.

## Still to do for submission

1. Record the 3–5 minute demo video.
2. Confirm the full 74-run [nightly report](docs/interoperability-report.md) matches
   the submitted application code; refresh evidence after implementation changes.
3. FR15: file F2 and F3 on `mosip/inji-verify`; report F10 to MOSIP privately first.
4. Commits from every teammate on `main`.
5. Make sure the committed person photo is a stand-in, not a real face.
