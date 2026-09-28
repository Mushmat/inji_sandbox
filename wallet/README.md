# Wallet (Holder)

Owns the holder side of the playground: Inji Web as the credential holder,
Mimoto as its backend-for-frontend, and the configuration that points them at
our own Certify instance. Covers FR1 (wallet side), FR3, and FR6 on the
holder side; FR4 (presentation) is next.

## Prerequisites

- Docker Desktop with at least 8 GB allocated (12 GB is more comfortable —
  this brings up five containers alongside Certify's three)
- Ports free: 3004, 8097, 8099, 9000, 9001, 55432
- The Certify stack from `../certify` running first, on the shared
  `mosip_network` — Mimoto resolves Certify by container name, not localhost

## Setup

### 1. Create the shared network (first time on a machine)

```bash
docker network create mosip_network
```

### 2. Bring up Certify

```bash
cd ../certify/docker-compose
docker compose up -d
```

Wait for it to report healthy. Mimoto will not be able to reach it otherwise.

### 3. Google OAuth credentials

Inji Web signs in with Google, so you need your own OAuth client — this cannot
be shared, it is tied to a Google account.

Google Cloud Console -> APIs & Services -> Credentials -> Create OAuth client ID
-> Web application:

| Field | Value |
|---|---|
| Authorised JavaScript origin | `http://localhost:8099` |
| Authorised redirect URI | `http://localhost:8099/v1/mimoto/oauth2/callback/google` |

Add your own Google account under **OAuth consent screen -> Test users**, or
sign-in is rejected as an unverified app.

Then:

```bash
cd docker-compose
cp .env.example .env     # fill in your client ID and secret
```

`.env` is gitignored. Do not commit it.

### 4. OIDC keystore

Mimoto needs `docker-compose/certs/oidckeystore.p12` holding the private key of
the OAuth client registered with the issuer's authorization server, under the
alias named by `client_alias` in `mimoto-issuers-config.json`.

For this demo both issuers use MOSIP's public `wallet-demo` sample client on
`esignet-mock.collab.mosip.net`, alias `wallet-demo-client`. That key pair is
published by MOSIP for sandbox use — it is in `../certify/scripts/issuance_flow.py`
as `PRIVATE_KEY_JWK`. Convert it to a PKCS12 entry:

```
alias    : wallet-demo-client
password : dummypassword          (matches oidc_p12_password in docker-compose.yml)
```

The `.p12` is gitignored, so each developer generates it locally.

> **If you replace the keystore after Mimoto has already run**, wipe its volume
> as well — `docker compose down -v`. Mimoto records key aliases in Postgres on
> first boot, and a keystore that no longer contains them fails at startup with
> `NoSuchSecurityProviderException: No such alias`.

### 5. Start the wallet

```bash
docker compose up -d
```

Open **http://localhost:3004** and sign in with Google.

## Ports

| Service | Port |
|---|---|
| Inji Web | 3004 |
| Mimoto (BFF) | 8099 |
| Data Share | 8097 |
| MinIO | 9000 / 9001 |
| Postgres | 55432 (5432 inside the network) |

## Issuers

`config/mimoto-issuers-config.json` defines what the wallet can download from.

| issuer_id | Points at | Notes |
|---|---|---|
| `Mock` | MOSIP Collab's hosted mock issuer | Upstream sample, left in place as a reference |
| `FarmerIssuer` | Our own Certify, `http://certify-nginx:80` | The one that matters |

`FarmerIssuer` uses the Docker-internal hostname on purpose. Mimoto calls the
credential endpoint server-side, so it resolves over `mosip_network`; the
browser never needs to reach that name.

## Verified working

Both mandatory formats download, verify and store, issued by our own Certify:

| Credential | Format | Result |
|---|---|---|
| Farmer Verifiable Credential | `ldp_vc` (W3C VC JSON-LD) | Stored |
| Farmer Verifiable Credential (SD-JWT) | `vc+sd-jwt` | Stored |

Test identity on the mock authorization server: individual ID `2154189532`,
OTP `111111`.

Signature verification is real: Mimoto resolves the issuer's `did:web` document
and checks the proof against the published public key. A mismatch, an
unreachable DID, or an unsupported format all fail loudly — see below.

## Known gaps (candidates for FR15)

**1. Mimoto 0.22.0 cannot accept `mso_mdoc`.** Certify issues ISO 18013-5 mDoc
credentials correctly, but the wallet rejects them at
`CredentialServiceImpl.buildCredentialRequest`:

```
java.lang.IllegalArgumentException: Unsupported credential format: mso_mdoc
```

MOSIP is aware — their own compose ships `IGNORED_ISSUER_IDS=MockMdl` to hide
their mDL issuer from Inji Web. A genuine gap between two modules of the same
stack, and the reason FR9 stays issuer-side only.

**2. `did:web` issuer identity does not survive multi-instance deployment.**
Certify generates its signing key on first boot into its own database, but the
DID document is published at a single URL. Two developers running Certify
produce two different keys, and only one can match what is published — every
credential from the other instance fails verification. Resolved here by seeding
a shared key (see `../certify`), but it is a real deployment gotcha worth
documenting: a credential that is otherwise valid is discarded outright when
the issuer's key cannot be resolved.

## Troubleshooting

**"Download Failed" immediately, before the login screen** — Mimoto could not
build the credential request. Almost always an unsupported format. Check:

```bash
docker logs mimoto-service --tail 200 | grep -i error
```

**"Download Failed" after a successful login** — the credential was issued but
failed verification. Compare the issuer's live DID document against the
published one; they must match exactly:

```bash
curl -s http://localhost:8090/v1/certify/.well-known/did.json
curl -s https://mushmat.github.io/inji_sandbox/did.json
```

**Mimoto cannot reach Certify** — confirm both are on the shared network:

```bash
docker exec mimoto-service curl -s -o /dev/null -w "%{http_code}" \
  http://certify-nginx:80/v1/certify/.well-known/openid-credential-issuer
```

Expect `200`.

**Mimoto will not start, `No such alias`** — the keystore changed after the
database recorded its aliases. `docker compose down -v` and start again.
