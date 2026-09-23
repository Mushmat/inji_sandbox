# API Documentation — Certify (Issuer)

Covers the two sets of APIs relevant to this component: the ones we
configured/exercised on our own Certify instance, and the external
authorization-server APIs the issuance flow depends on. Full upstream API
reference: https://mosip.stoplight.io/docs/inji-certify

## Our Certify instance (`http://localhost:8090/v1/certify`)

### `GET /.well-known/openid-credential-issuer`

OpenID4VCI issuer metadata. Lists every configured credential type, its
format, scope, claims, and supported signing/binding methods. This is the
first thing any wallet or playground UI should query to discover what
Certify can issue.

<details>
<summary>Example response (abridged)</summary>

```json
{
  "credential_issuer": "http://certify-nginx:80",
  "authorization_servers": ["https://esignet-mock.collab.mosip.net"],
  "credential_endpoint": "http://certify-nginx:80/v1/certify/issuance/credential",
  "credential_configurations_supported": {
    "FarmerCredential": {
      "format": "ldp_vc",
      "scope": "mock_identity_vc_ldp",
      "credential_signing_alg_values_supported": ["EdDSA"],
      "credential_definition": {
        "type": ["FarmerCredential", "VerifiableCredential"],
        "@context": ["https://www.w3.org/2018/credentials/v1"]
      }
    },
    "FarmerCredentialSdJwt": {
      "format": "vc+sd-jwt",
      "scope": "mock_identity_vc_ldp",
      "vct": "FarmerCredentialSdJwt",
      "credential_signing_alg_values_supported": ["EdDSA"]
    },
    "MobileDrivingLicense": {
      "format": "mso_mdoc",
      "scope": "mock_identity_vc_ldp",
      "doctype": "org.iso.18013.5.1.mDL",
      "credential_signing_alg_values_supported": ["ES256"]
    }
  }
}
```
</details>

### `GET /.well-known/did.json`

The issuer's DID document — used by verifiers to resolve the public key that
signed a credential. Set to `did:web:mushmat.github.io:inji_sandbox`; see the
README's "DID hosting" section for how it gets published.

### `POST /credential-configurations`

Registers a new credential type. This is how `FarmerCredentialSdJwt` was
added — no source code change, just a REST call against the running
instance (also seeded automatically via SQL for fresh deployments, see
`docker-compose/certify_init.sql`).

<details>
<summary>Example request (SD-JWT format)</summary>

```json
{
  "credentialConfigKeyId": "FarmerCredentialSdJwt",
  "vcTemplate": "<base64-encoded Velocity template>",
  "credentialFormat": "vc+sd-jwt",
  "didUrl": "did:web:<issuer DID host>",
  "keyManagerAppId": "CERTIFY_VC_SIGN_ED25519",
  "keyManagerRefId": "ED25519_SIGN",
  "signatureAlgo": "EdDSA",
  "sdClaim": "$.credentialSubject.farmerID",
  "sdJwtVct": "FarmerCredentialSdJwt",
  "scope": "mock_identity_vc_ldp",
  "displayOrder": ["fullName", "mobileNumber", "..."],
  "metaDataDisplay": [{"name": "Farmer Verifiable Credential (SD-JWT)", "locale": "en"}],
  "sdJwtClaims": {"fullName": {"display": [{"name": "Full Name", "locale": "en"}]}},
  "pluginConfigurations": [{
    "mosip.certify.mock.data-provider.csv.identifier-column": "id",
    "mosip.certify.mock.data-provider.csv.data-columns": "id,fullName,...",
    "mosip.certify.mock.data-provider.csv-registry-uri": "/home/mosip/config/farmer_identity_data.csv"
  }],
  "credentialStatusPurposes": ["revocation"]
}
```

Response: `{"id": "FarmerCredentialSdJwt", "status": "active"}` (HTTP 201).
</details>

**Gotcha worth knowing**: for `vc+sd-jwt`, `signatureCryptoSuite` must be
**omitted entirely**, not just left null. Certify's own validator
(`SdJwtCredentialConfigValidator`) treats its presence as "this isn't really
SD-JWT" and rejects the request with a misleading
`vc_sd_jwt_mandatory_fields_missing` error that reads like `vct` or
`signatureAlgo` is missing, even when both are present correctly.

For `mso_mdoc` it's the opposite: `signatureCryptoSuite` is **required**
(`EcdsaSecp256r1Signature2019` for the `ES256`/`EC_SECP256R1_SIGN` key we
use), `sdJwtVct`/`sdJwtClaims`/`credentialSubjectDefinition` must all be
absent, and it needs its own fields — `doctype` (`org.iso.18013.5.1.mDL`) and
`msoMdocClaims` (namespace → claim → display, note the namespace here is
`org.iso.18013.5.1.mDL`, *with* the doctype suffix — different from the
`vcTemplate`'s own namespace key `org.iso.18013.5.1`, *without* it; MOSIP's
own test fixtures use this same inconsistency, not something we introduced).

### `POST /issuance/credential`

The actual OpenID4VCI credential endpoint. Requires a Bearer access token
(from the authorization server, see below) and a signed holder proof JWT.
Request body differs slightly by format:

```json
// ldp_vc
{"format": "ldp_vc", "credential_definition": {"type": [...], "@context": [...]}, "proof": {"proof_type": "jwt", "jwt": "..."}}

// vc+sd-jwt
{"format": "vc+sd-jwt", "vct": "FarmerCredentialSdJwt", "proof": {"proof_type": "jwt", "jwt": "..."}}

// mso_mdoc
{"format": "mso_mdoc", "doctype": "org.iso.18013.5.1.mDL", "proof": {"proof_type": "jwt", "jwt": "..."}}
```

The holder proof JWT must include `aud` (Certify's own domain, matching
`mosip.certify.identifier`), `nonce` (the `c_nonce` from the token response),
`iss` (the OAuth client ID), and — easy to miss — **`iat`**. Certify's claims
verifier requires `iat` unconditionally
(`JwtProofValidator.DEFAULT_REQUIRED_CLAIMS = {"aud", "iat"}`), but a missing
`iat` surfaces as `invalid_proof` / *"Error encountered during proof jwt
parsing"* — worded like a parsing failure, not a missing-claim failure.

**Holder key type depends on format.** `ldp_vc` and `vc+sd-jwt` both worked
fine with an RSA holder key in the proof JWT's `jwk` header. `mso_mdoc`
doesn't: it failed with `Unsupported curve for EC2 key type: null`, because
mDoc device-key binding goes through COSE_Key, which only supports elliptic
curve keys (EC2), not RSA. Fix: generate an EC P-256 key (`crv: "P-256"`) and
sign the proof JWT with `ES256` instead of `RS256` when requesting `mso_mdoc`
— everything else about the flow is identical.

## Authorization server (MOSIP Collab's mock eSignet)

Certify itself doesn't handle login — that's delegated to
`https://esignet-mock.collab.mosip.net/v1/esignet`, a public MOSIP sandbox.
No account setup needed: it ships a pre-registered demo OAuth client
(`clientId: wallet-demo`) with a published test key pair, plus a sample
identity (`individualId: 2154189532`, mock OTP always `111111`).

Full flow, reproduced by `scripts/test_issuance_flow.py`:

1. `GET /csrf/token` — session CSRF token
2. `POST /authorization/v2/oauth-details` — starts the auth transaction (PKCE
   challenge, requested scope)
3. `POST /authorization/send-otp` — triggers the mock OTP
4. `POST /authorization/v3/authenticate` — submits OTP `111111`
5. `POST /authorization/auth-code` — issues the authorization code
6. `POST /oauth/v2/token` — exchanges the code for an access token, using a
   `client_assertion` JWT (signed with `wallet-demo`'s private key) plus the
   PKCE `code_verifier`
7. `POST {certify}/issuance/credential` — the actual credential request,
   described above

**Gotcha worth knowing**: a credential-configuration's `scope` value is not
automatically valid on the authorization server. `mock_identity_vc_ldp`
worked because it's the scope shipped with (and pre-registered for)
`wallet-demo` in the upstream sample; a custom scope we initially tried
(`mock_identity_vc_sd_jwt`) was rejected by the auth server with
`invalid_scope`, even though Certify itself accepted it fine when the config
was created. Registering a new OAuth client with a custom scope requires
privileged MOSIP Partner Management System credentials, which is
infrastructure we don't own — so instead, `FarmerCredentialSdJwt` reuses the
already-registered `mock_identity_vc_ldp` scope. This is legitimate, not a
workaround: Certify resolves which credential to issue by matching scope
*and* `format`/`vct` together
(`VCIssuanceUtil.getScopeCredentialMapping`), so one OAuth scope covering
multiple credential-format variants of the same underlying data is a
supported pattern.

## Example verified output

Both captured from a real run against the local instance — see
`scripts/test_issuance_flow.py` to reproduce.

**JSON-LD** — valid `Ed25519Signature2020` proof, correct claims:
```json
{
  "credential": {
    "type": ["VerifiableCredential", "FarmerCredential"],
    "credentialSubject": {"fullName": "Gorge Cooper", "farmerID": "987654321", "...": "..."},
    "issuer": "did:web:...",
    "proof": {"type": "Ed25519Signature2020", "proofPurpose": "assertionMethod", "...": "..."}
  }
}
```

**SD-JWT** — decoded payload shows correct `vct`, `_sd` digest, and `cnf`
holder binding; the credential string's `~`-separated suffix is the
disclosure for the selectively-disclosable `farmerID` claim:
```json
{"vct": "FarmerCredentialSdJwt", "_sd": ["<digest>"], "cnf": {"kid": "did:jwk:..."}}
```
```
disclosure: ["<salt>", "farmerID", "987654321"]
```

**mDoc/mDL** — the credential itself is base64url-encoded CBOR (not JSON);
decoded, it's a genuine ISO 18013-5 `IssuerSigned` structure with a
COSE_Sign1-signed MSO (including the X.509 signing cert chain) and the
actual claims:
```json
{
  "docType": "org.iso.18013.5.1.mDL",
  "issuerSigned": {
    "issuerAuth": "<COSE_Sign1: protected headers, X.509 cert chain, signature>",
    "nameSpaces": {
      "org.iso.18013.5.1": [
        {"elementIdentifier": "family_name", "elementValue": "Cooper"},
        {"elementIdentifier": "given_name", "elementValue": "Gorge"},
        {"elementIdentifier": "birth_date", "elementValue": "25-05-1990"},
        {"elementIdentifier": "document_number", "elementValue": "987654321"}
      ]
    }
  }
}
```

## Editable identity data (demo UI only)

`demo-ui/server.py` exposes two extra endpoints backing the identity editor
in the UI — not part of Certify itself, just our own convenience layer over
the CSV file Certify's data-provider plugin reads.

- `GET /api/identity` — returns the current editable fields for the one
  identity the demo issues credentials for.
- `POST /api/identity` — takes a JSON body of field → value, writes it back
  to `farmer_identity_data.csv`, **then restarts the `certify` container**
  and waits (up to 3 minutes) for it to report healthy before responding.

The restart is required, not optional: the bundled `MockCSVDataProviderPlugin`
loads the CSV once at container startup and doesn't re-read it per request —
confirmed by testing directly (editing the file alone left the next issued
credential unchanged; a restart picked up the edit). So this endpoint
genuinely takes ~1-2 minutes; the UI shows a "restarting" state for exactly
that reason, and callers should expect a slow response, not treat it as
hung.
