# Patches for certify/scripts/issuance_flow.py

Two independent, small changes for Chirayu to review. Apply the holder-key one first.

## 1. issuance_flow_holder_key.patch

`issuance_flow_holder_key.patch` — for Chirayu to review and apply. Made against the current
`issuance_flow.py` (md5 `964994fd7257c0c4a4574ba2e43e1e43`).

**Why:** to present a credential, the wallet has to sign with the same key the credential was issued
to. `run_issuance()` generates a new holder key each time and never returns it, so no one can present
what it issues.

**What it changes:**
- `run_issuance(vc_format, holder_key=None)`: optional private key (EC P-256 → ES256 proof,
  Ed25519 → EdDSA, RSA → RS256). mDoc still requires EC P-256.
- The result also includes `holder_jwk` (the public key the credential is bound to).
- Without `holder_key` nothing changes: same throwaway keys, same steps, same output (plus `holder_jwk`).
  His CLI, tests and demo UI don't need edits.

**Apply** (repo root):

```bash
git apply --check verify/patches/issuance_flow_holder_key.patch && git apply verify/patches/issuance_flow_holder_key.patch
```

`verify/` detects whether it's applied and says so in the CLI, the tests and the demo UI.

## 2. issuance_flow_iat_wait.patch

**Why:** Certify 0.14.0 accepts an access token only if its `iat` is strictly before Certify's clock, with no
leeway (FINDINGS F12). On a laptop whose clock is slightly behind Collab eSignet's, the credential request
right after the token exchange fails with `401 invalid_token`. Found live: Chirayu's unmodified flow failed
this way on a Windows laptop; this patch fixed it (syncing the clock also helps).

**What it changes:** before *Request the credential*, reads the token's `iat` and sleeps until it is 1 s in
the past on this machine (0 s when the clock is fine, never more than 10 s). No other behaviour changes.

```bash
git apply --ignore-whitespace verify/patches/issuance_flow_iat_wait.patch
```

## 3. certify_keep_keys.patch — superseded

Written for the older `feature/certify-issuer` compose file. On `feature/wallet` the keystore mount is already
fixed (Navish found the same bug), and the team's shared seeded key (certify/README, "Running this issuer on
another machine") replaces the need to preserve per-machine keys. Only its first hunk (a named database volume)
still applies there, and with the shared seed it's optional.
