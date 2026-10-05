# Status — Inji Interoperability Playground

Last updated: 2026-10-05

## Summary

The three pipelines (Certify, the wallet, Present & Verify) are integrated and run
together from one command, with the Playground on top: one page that runs issue →
hold → present → verify across any issuer, wallet and verifier, shows every protocol
message, and records whether each module behaved the way the standards say it should.
All mandatory requirements (FR1–FR7) work and have been tested by hand end to end,
including the real Inji Web wallet. Most good-to-have and bonus items are done too.

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

**Tests.** 33 backend tests (every tamper scenario against the Playground verifier over
real HTTP, offline), 10 frontend tests, 35 offline verifier tests, 14 live Certify
tests. GitHub runs the offline suites on every push, and the full matrix every night.

## What we found

Inji Verify 0.18.2 accepts a wrong credential type (F2), an SD-JWT replayed from another
session (F3), and a credential signed by someone else's key that names Certify as the
issuer (F10). The Playground verifier catches all three. The full list, with how to
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
2. Commit a full-matrix report as `docs/interoperability-report.md` (from a passing
   nightly run's artifact) and remove the old quick-matrix one at the repo root.
3. FR15: file F2 and F3 on `mosip/inji-verify`; report F10 to MOSIP privately first.
4. Commits from every teammate on `main`.
5. Make sure the committed person photo is a stand-in, not a real face.
