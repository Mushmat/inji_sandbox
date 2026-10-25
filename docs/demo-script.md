# Four-minute submission demo

This is a recording script, not a claim that a full-stack video has been recorded. Record the actual browser and services; do not replace failures with edited success screens. A complete local Inji Web recording still needs the team OAuth configuration, shared issuer keystore/seed and an allowed Google test user.

Before recording, complete the [private-file setup](../README.md#run-it), then run `python3 integration/stack.py up` and `python3 integration/stack.py status`; open `http://localhost:5050`. Check the DID key match, issuer, Mimoto and Verify readiness. Confirm that the sample subject and photo are synthetic stand-ins before recording; their provenance is a pending checklist item. Download a new card during the run. Scripted issuance exposes the exchange; Mimoto's internal exchanges are not captured in the pinned implementation. Label the actual wallet and its version.

| Time | On screen | What to explain |
|---|---|---|
| 0:00–0:25 | Selector and health dots | Certify issues, Inji Web holds/presents, Inji Verify verifies. Name the actual module versions. |
| 0:25–1:25 | JSON-LD run; download in Inji Web | Show the real wallet download and return to continue. Use the scripted flow to inspect token/credential exchanges; keep token values out of the final video. |
| 1:25–2:15 | Presentation link/QR and wallet consent | Show the authorization request, presentation definition and consent, then the verifier result. Explain which real-wallet proof checks were unavailable. |
| 2:15–2:55 | SD-JWT run | Use the scripted wallet and explicitly identify it. The pinned Inji Web cannot present SD-JWT. Show disclosure and key-binding checks. |
| 2:55–3:30 | Altered-claim or replay scenario | Explain expected rejection and show the actual result. If an upstream module accepts it, show the resulting FAIL finding. |
| 3:30–4:00 | Sequence diagram, history, report and flow health | Export the report; distinguish implemented capabilities, executed evidence and unsupported mdoc paths. |

If the private files are unavailable, the synthetic issuer and scripted wallet can demonstrate the presentation/verification harness against real Inji Verify. Label that as a limited demonstration; it does not fulfill the real Certify-to-Inji-Web issuance portion above. [The recorded matrices](interoperability-report.md) and [acceptance checklist](submission-checklist.md) provide separate evidence.

Recording acceptance: 3–5 minutes, readable inspector, complete issue → hold → present → verify cycle, participant/format labels visible, no access tokens or private keys, and all unsupported/skipped paths described accurately. Add the final video URL to the submission checklist after the recording exists.
