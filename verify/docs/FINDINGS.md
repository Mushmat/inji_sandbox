# Present & Verify: interoperability findings

What we found while wiring Inji Certify credentials into Inji Verify over OpenID4VP. Each entry says
**how it was found** and **how to confirm it live**. Don't file an issue upstream until the live run
has been done and its output is attached.

Versions read: Inji Verify `v0.18.2` (verify-service), vc-verifier `v1.8.1`, Inji Certify `v0.14.0`.
Numbering matches the team's main findings list (`claude/interop-findings.md` in the project).

| # | Component | Finding | Evidence | Status |
|---|---|---|---|---|
| F2 | Inji Verify | `presentation_definition` constraints are not checked against the submitted credential | Source + **live** | **Confirmed live** (both formats) |
| F3 | Inji Verify | SD-JWT key-binding `nonce` / `aud` not compared with the session (replay) | Source + **live** | **Confirmed live** |
| F4 | Inji Verify | PD model keeps only `path`, `filter.type`, `filter.pattern` | Source (DTOs) | Confirm live |
| F6 | Inji Verify | Upstream `docker-compose/db-init/init.sql` is behind the 0.18.2 schema | Source | Worked around (our schema ran fine live) |
| F8 | vc-verifier (Inji Verify) | `RsaSignature2018` presentation proofs are never verified, though advertised | Source | Confirm live |
| F9 | Inji Certify ↔ Inji Verify | Certify writes `did:jwk` with base64 `=` padding; Inji Verify rejects it | **Live** + source | **Confirmed live** |
| F10 | Inji Verify (vc-verifier) | Issuer's signing key is never tied to the issuer: any key "verifies" | **Live** + source | **Confirmed live** (both formats) |
| F11 | Inji Verify (vc-verifier) | SD-JWT issuer key taken only from `x5c`; `kid` / DID / issuer metadata ignored | **Live** + source | **Confirmed live** |
| F12 | Inji Certify | Access token `iat` checked with zero clock tolerance | **Live** + source | **Confirmed live** |
| M1 | Inji Verify | mDoc cannot be presented over OpenID4VP | Source | Found in source |
| W2 | Inji Web / Mimoto 0.22 (inji-openid4vp 0.7.0) | Only accepts an `https://` response_uri with a dotted host and **no port** | **Live** + source | **Confirmed live** |
| W3 | Inji Web / Mimoto 0.22 | Always signs presentations with its Ed25519 key, whatever key the credential is bound to | **Live** + source | **Confirmed live** |
| W4 | Mimoto 0.22 ↔ Certify | Mimoto only knows the alg name `Ed25519`; Certify configs say `EdDSA` (or nothing) | **Live** + source | **Confirmed live** |
| W5 | Inji Web / Mimoto 0.22 | Cannot present SD-JWT over OpenID4VP (credential matching is ldp_vc only) | **Live** + source | **Confirmed live** |
| W6 | Inji Web / Mimoto 0.22 | Pre-registered verifier needs `allow_unsigned_request: true`, or unsigned requests are refused | **Live** + source | **Confirmed live** |
| D1 | Our setup | The hosted `did.json` must match Certify's current keys | **Live** | **Confirmed live** — currently stale |
| N1 | Ecosystem | `vc+sd-jwt` vs `dc+sd-jwt` | Source + specs | Informational |

## Live results — 2026-09-29, Windows 11 laptop

Inji Verify 0.18.2 (`injistack/inji-verify-service:0.18.2`) and Inji Certify 0.14.0 in Docker, Collab eSignet
for login, run with `test_presentation_flow.py <format> all`. Two credential sources: **Certify** (Chirayu's
issuance flow) and the **offline test issuer** (`did:key`, used to test Inji Verify without D1 in the way).

| format | scenario | expected | Certify credential | test-issuer credential | what it shows |
|---|---|---|---|---|---|
| JSON-LD | honest | VALID | VALID ✓ | VALID ✓ | (before the shared key: INVALID, D1) |
| JSON-LD | altered | INVALID | INVALID ✓ | INVALID ✓ | issuer signature catches it |
| JSON-LD | replay | INVALID | REJECTED ✓ | REJECTED ✓ | `NONCE_VALIDATION_FAILED` at submission — correct |
| JSON-LD | wrong type | INVALID | **VALID ✗** | **VALID ✗** | **F2** |
| JSON-LD | forged issuer | INVALID | **VALID ✗** | **VALID ✗** | **F10** |
| SD-JWT | honest | VALID | VALID ✓ | VALID ✓ | |
| SD-JWT | altered | INVALID | INVALID ✓ | INVALID ✓ | disclosure digest catches it |
| SD-JWT | replay | INVALID | **VALID ✗** | **VALID ✗** | **F3** |
| SD-JWT | wrong type | INVALID | **VALID ✗** | **VALID ✗** | **F2** |
| SD-JWT | forged issuer | INVALID | **VALID ✗** | **VALID ✗** | **F10** |
| JSON-LD | expired | VALID BUT EXPIRED | — | VALID BUT EXPIRED ✓ | (04:50; Certify can't issue an expired credential) |
| SD-JWT | expired | VALID BUT EXPIRED | — | VALID BUT EXPIRED ✓ | |

The Certify column is from the rerun at 03:50 with the team's shared signing key (D1 fixed on the laptop).
The "forged issuer" row doesn't use a Certify credential in either column (the attacker makes their own), so
both columns are the same test run twice.

Before we got here, two things broke the run and are findings in their own right: every Certify JSON-LD
presentation first failed with Inji Verify `500 VP_VERIFICATION_FAILED` (**F9**), and every issuance failed with
`401 invalid_token` until the laptop clock was synced (**F12**).


### Real wallet: Inji Web → Inji Verify (2026-09-29, 04:39)

Navish's Inji Web 0.17 + Mimoto 0.22 on the same laptop, Farmer cards downloaded from our Certify (shared key),
request opened with the demo page's **Open in Inji Web** button.

| format | result | why |
|---|---|---|
| JSON-LD, first try | wallet refused the request | W6, then W2 (fixed with `allow_unsigned_request` and an https tunnel) |
| JSON-LD, card bound to ES256 | Inji Verify **INVALID** (holder mismatch) — correct | W3 + W4 |
| JSON-LD, card re-downloaded after adding `Ed25519` to Certify's proof algs | Inji Verify **VALID**, all playground checks pass ✓ | full MOSIP chain works |
| SD-JWT | wallet: "No matching credentials found (Missing: farmerID, vct)" | W5 — Inji Web can't present SD-JWT; the built-in wallet covers it (VALID live) |

---

## F2. The credential is not checked against the presentation_definition

**What:** `VerifiablePresentationSubmissionServiceImpl.isVPTokenNotMatching()` only checks that the
token, descriptor map and request are non-null. No input-descriptor constraint (credential `type`,
`vct`, required fields) is evaluated. vc-verifier checks signatures, expiry and status only.

**Expected:** DIF Presentation Exchange 2.0 / OpenID4VP: the verifier checks that the presented
credential satisfies the input descriptor it claims to answer.

**Reproduce:** scenario **Wrong credential type**. The request asks for `LandOwnershipCredential`
(SD-JWT: `vct` `LandOwnershipCredentialSdJwt`); the wallet sends its `FarmerCredential` anyway.
The playground check *Credential meets the presentation_definition constraints* fails.

**Confirmed live (2026-09-29):** Inji Verify returned `allChecksSuccessful: true` for both formats.

## F3. SD-JWT key binding is not tied to the verifier session

**What:** for JSON-LD presentations, `submit()` compares `proof.challenge` with the stored nonce and
`proof.domain` with the client id (400 `NONCE_VALIDATION_FAILED` otherwise). SD-JWT presentations
skip that block (they are not JSON), and vc-verifier's SD-JWT validation checks that the KB-JWT has a
`nonce` and `aud`, but is never given the session's values to compare with.

**Impact:** an SD-JWT presentation captured from one session can be replayed into another session
of the same verifier.

**Reproduce:** SD-JWT, scenario **Replayed presentation**: the flow presents to session 1, then posts
the same `vp_token` to session 2. Playground check *KB-JWT nonce is this session's nonce* fails.
The same scenario with JSON-LD is refused at submission, which is the correct behaviour to compare with.

**Confirmed live (2026-09-29):** session 2 accepted the replayed SD-JWT as `VALID`, with a Certify credential
and with a test-issuer one.

## F4. presentation_definition features are dropped

**What:** `VPDefinitionResponseDto` / `InputDescriptorDto` / `FieldDTO` / `FilterDTO` keep only `path`,
`filter.type` and `filter.pattern`. `limit_disclosure`, `const`, `contains`, `enum` and `optional`
disappear silently; the top-level `format` only knows `jwt`, `jwt_vc`, `ldp_vc`.

**Consequence here:** `scripts/pex.py` builds requests with `pattern` filters and per-descriptor
`format` only, so what Inji Verify stores is what we meant. Compare the PD in the "create request"
step's request and response bodies to see the round trip.

## F6. Upstream compose database script is out of date

`inji-verify/docker-compose/db-init/init.sql` at v0.18.2 has `vp_token NOT NULL` and lacks
`response_code`, `response_code_expiry_at`, `response_code_used`, which the 0.18.2 entity writes
(`ddl-auto=none`). `docker-compose/db-init/verify_init.sql` here is assembled from the authoritative
`db_scripts/inji_verify/ddl` instead (loads cleanly into Postgres; checked).

## F8. RsaSignature2018 presentation proofs are never verified

**What:** vc-verifier 1.8.1 `PresentationVerifier.verifyPresentationProof()` has branches for
Ed25519Signature2018/2020, EcdsaSecp256k1/r1Signature2019 and JsonWebSignature2020, and
`else -> false`. There is no RsaSignature2018 branch, yet `CredentialValidatorConstants.PROOF_TYPES_SUPPORTED`
lists `RsaSignature2018`, and the Inji Verify SDK advertises it in `client_metadata.vp_formats.ldp_vp`.

**Impact:** a wallet with an RSA holder key signs its presentation with RsaSignature2018 as told, and
Inji Verify reports the holder proof as invalid. Chirayu's `vp_request_config.json` also asks for
`RsaSignature2018`.

**What we did:** the built-in wallet uses an EC P-256 key (Certify's FarmerCredential config accepts
ES256 proofs) and signs presentations with JsonWebSignature2020 / ES256, which vc-verifier does check.

**Confirm live:** present a JSON-LD credential bound to an RSA key with an RsaSignature2018 VP proof.

## F9. Certify's did:jwk has base64 padding, and Inji Verify rejects it

**Seen live:** every JSON-LD presentation of a Certify credential came back from Inji Verify as
`500 VP_VERIFICATION_FAILED`; its log said `Given did url is not supported`.

**Why:** Certify 0.14.0 builds the holder's `did:jwk` (in `credentialSubject.id`) with standard base64
padding, e.g. `did:jwk:eyJr…In0=`. The did:jwk method requires base64url **without** padding (RFC 7515).
vc-verifier's `DidPublicKeyResolver.DID_MATCHER` doesn't allow `=` in a method-specific id, so when the
wallet signs its presentation as that DID, Inji Verify can't resolve the key — and turns it into a 500, not an
"invalid" result.

**Impact:** a wallet that presents exactly the DID Certify wrote (the natural thing to do) can never be verified
by Inji Verify. Two MOSIP components disagree on one DID encoding.

**Workaround in `verify/`:** the wallet presents the unpadded form of the same DID (`wallet.holder_did_for`).
vc-verifier's holder-binding check decodes both and compares keys, so this passes.

## F10. The issuer's signing key is never tied to the issuer

**Seen live (both formats):** scenario *Forged issuer*. The attacker makes a FarmerCredential that names
Certify as issuer (`did:web:mushmat.github.io:inji-did`, or SD-JWT `iss` = Certify's `http://certify-nginx:80`)
and signs it with **their own** key. Inji Verify: `VALID`, all checks green.

**Why (vc-verifier 1.8.1):**
- JSON-LD: `LdpVerifier.verify()` resolves `proof.verificationMethod` and checks the signature with that key.
  Nothing checks that the verification method belongs to the `issuer` DID. A `did:key` signature "verifies" a
  credential that says it is from `did:web:…`.
- SD-JWT: `SdJwtVerifier` takes the key from the certificate in the JWT's own `x5c` header and does not
  validate the certificate against any trust anchor or against `iss`. A self-signed certificate is enough.

**Expected:** VC Data Integrity requires the verification method to be controlled by the issuer; SD-JWT VC
requires the issuer key to be tied to `iss` (issuer metadata, DID, or an `x5c` chain to a trusted root).
A relying party can add its own issuer allow-list on top, but the signature check itself should not pass.

**Impact:** anyone can mint credentials that Inji Verify reports as valid "from" any issuer. This is the most
serious finding here; report it privately to MOSIP first rather than as a public issue.

## F11. SD-JWT issuer key only from x5c

vc-verifier's `SdJwtVerifier` reads the key only from `x5c` (`No X.509 certificate found in JWT header` /
`getX509CertChain(...) must not be null` otherwise). An SD-JWT VC whose issuer key is published through a DID
(`kid`) or `/.well-known/jwt-vc-issuer` — both allowed by SD-JWT VC — is always rejected. Seen live with the
test issuer before it added `x5c`. Certify sends `x5c`, so Certify SD-JWTs work.

## F12. Certify rejects access tokens on a sub-second clock difference

**Seen live:** Chirayu's unmodified issuance flow failed at *Request the credential* with `401 invalid_token`;
Certify's log: `The iat claim is not valid`. The laptop clock was ~1 s behind Collab eSignet.

**Why:** Certify 0.14.0 `AccessTokenValidationFilter` validates `iat` with `iat.isBefore(Instant.now())` and no
leeway. A token used within a second of being issued fails whenever the issuer's clock is even slightly ahead.
RFC 7519 recommends allowing a small leeway; Spring's own timestamp validator defaults to 60 s.

**Fixes:** `patches/issuance_flow_iat_wait.patch` makes the flow wait until the token's `iat` has passed on the
local clock (at most 10 s) before requesting the credential — this is what fixed it here. Syncing the clock helps too.

## M1. mDoc cannot be presented over OpenID4VP

`VerifiablePresentationSubmissionServiceImpl.processSingleToken()` keeps a `vp_token` only if it is a
JSON object, an SD-JWT (`typ` `vc+sd-jwt` / `dc+sd-jwt`), or base64url-encoded JSON. An mDoc
`DeviceResponse` (base64url CBOR) is dropped and the submission fails with `INVALID_VP_TOKEN`. Inji
Verify checks mDocs only through its QR/upload path. The demo UI shows mDoc as unavailable with this reason.

## W2. Inji Web only sends presentations to https addresses without a port

inji-openid4vp 0.7.0 (`common/Utils.kt`) validates `response_uri` with
`^https://(?:[\w-]+\.)+[\w-]+(?:/...)*` — https only, a dotted host, and no `:port`. A local Inji Verify
(`http://localhost:8082`, `http://verify-service:8080`) is refused with `response_uri data is not valid`, so
Inji Web can't present to a locally run Inji Verify at all without an https front. **Workaround:** a Cloudflare
quick tunnel (`cloudflare/cloudflared` on `mosip_network`) and `VERIFY_PUBLIC_URL=https://<tunnel-host>`.
Requiring https matches HAIP-style profiles; rejecting any explicit port is a bug.

## W3. Mimoto always signs presentations with Ed25519

`WalletPresentationServiceImpl.DEFAULT_SIGNING_ALGORITHM_NAME = "ED25519"`: every presentation is signed with the
wallet's Ed25519 key. At download, though, Mimoto binds the credential to the first algorithm the issuer supports
from `ED25519,ES256K,ES256,RS256`. Our FarmerCredential accepted only RS256/ES256, so the card was bound to an EC
key and every presentation failed holder binding in Inji Verify (**live**: `ERR_HOLDER_BINDING_CHECK_FAILED`).
Mimoto should sign with the key the credential is bound to. Also in the same area: Mimoto's wallet metadata
advertises `ldp_vc` proof type `"EEd25519Signature2020"` (typo) in `OpenID4VPService`.

## W4. "Ed25519" vs "EdDSA"

Mimoto's `SigningAlgorithm.fromString` knows `RS256, ES256, ES256K, ED25519` — not `EdDSA` (RFC 8037's name, used by
our SD-JWT config). So an issuer listing only `EdDSA` never gets Ed25519 proofs from Mimoto. **Fix used:** list both
`EdDSA` and `Ed25519` in `proof_signing_alg_values_supported` for both Farmer configs (SQL in
`patches/certify_add_ed25519_proof_alg.sql`); Certify then accepts Mimoto's Ed25519 proof, and presentations verify.
This also changes F5's picture: Certify's default `Ed25519` matches Mimoto, while RFC 8037 wallets send `EdDSA`.

## W5. Inji Web cannot present SD-JWT

`CredentialMatchingServiceImpl.matchesFormat()` returns false unless the stored credential **and** the input
descriptor are `ldp_vc`, and `getCredentialData()` throws "SD-JWT credential format ... is not supported for
credential matching". **Live:** an SD-JWT request shows "No matching credentials found — Missing: farmerID, vct",
which misleads (the card is there; the format is unsupported). So FR6's second format needs another holder for
presentation: the built-in wallet in `verify/` presents SD-JWT to Inji Verify (VALID live). Minor: Mimoto's
`matchesFilter` treats `filter.pattern` as a substring, not a regular expression.

## W6. Pre-registered verifiers need allow_unsigned_request

inji-openid4vp's `PreRegisteredSchemeAuthorizationRequestHandler.isUnsignedRequestSupported()` returns the
verifier entry's `allowUnsignedRequest` (default false). Inji Verify 0.18.2 sends unsigned requests by value, so the
entry in `mimoto-trusted-verifiers.json` needs `"allow_unsigned_request": true` (Mimoto's `VerifierDTO`), or the
wallet fails with "unsigned request is not supported for given client_id_scheme - pre-registered". MOSIP's own
sample entry doesn't set it.

## D1. Every Certify must sign with the shared key (our setup)

Certify generates signing keys per database, but `did:web:mushmat.github.io:inji_sandbox` (and the older
`inji-did`) publish one fixed key pair. A Certify started from scratch signs with its own keys, so every
verifier (Inji Verify, and Mimoto for Inji Web) rejects its credentials. **Seen live 2026-09-29** on the demo
laptop: its Certify had keys `zDnaetBp…` / `z6Mkw3ko…`; the published document has `zDnaebkv…` / `z6Mkgin2…`.

**Team fix (feature/wallet branch, certify/README "Running this issuer on another machine"):** the team shares
one seeded key privately — `data/CERTIFY_PKCS12/local.p12` plus `keys_seed.local.sql` (both git-ignored) — and
every Certify loads it through a `docker-compose.override.yaml`. Do **not** republish `did.json` from one
machine; that would break everyone else's Certify. The playground check *Published DID document has Certify's
current keys* tells you when a Certify isn't using the shared key.

Related compose bug, found independently by Navish and here: the keystore was mounted at `/home/mosip/...`
while Certify 0.14.0 writes `/home/inji/...` (fixed on feature/wallet).

## N1. SD-JWT format name

Inji Certify and Inji Verify use `vc+sd-jwt`; newer SD-JWT VC drafts and OpenID4VP 1.0 use `dc+sd-jwt`.
Inji Verify 0.18.2 already accepts both `typ` values (`Utils.VALID_SD_JWT_TYPES`), so this matters for
other wallets/verifiers that know only one of the names, not for Inji Verify itself.
