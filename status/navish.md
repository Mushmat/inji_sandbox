# Status — Navish — Wallet (Inji Web + Mimoto)

Last updated: 2026-09-29

## Summary

The wallet side is running and verified. Inji Web and Mimoto are up locally,
pointed at our own Certify, and both mandatory credential formats download,
pass signature verification, and store. FR1 (wallet side), FR3, and the holder
half of FR6 are complete. FR4 (presentation) has not been started.

## What's done

**Wallet running against our own issuer**
- Mimoto + Inji Web + Data Share + MinIO + Postgres via Docker Compose
- `FarmerIssuer` added to `mimoto-issuers-config.json`, pointing at our Certify
- Mimoto and Certify share the `mosip_network` Docker network, declared in
  compose rather than attached by hand
- Google OAuth client created for Inji Web sign-in; credentials in a gitignored
  `.env`, with `.env.example` committed

**Both mandatory formats verified end to end**

| Credential | Format | Result |
|---|---|---|
| Farmer Verifiable Credential | `ldp_vc` | Downloaded, verified, stored |
| Farmer Verifiable Credential (SD-JWT) | `vc+sd-jwt` | Downloaded, verified, stored |

Verification is genuine — Mimoto resolves the issuer's `did:web` document and
checks the proof against the published public key. Confirmed by watching it
fail correctly on a key mismatch and on an unresolvable DID before the fix.

**Documentation**
- `wallet/README.md` — setup, ports, issuer config, known gaps, troubleshooting

## Bugs found and fixed

1. **Certify's PKCS12 volume mount pointed at the wrong path.** Compose mounted
   `./data/CERTIFY_PKCS12` to `/home/mosip/CERTIFY_PKCS12`, but Certify's
   working directory is `/home/inji`, so the master keystore was never
   persisted to the host. `docker compose down` followed by `up` without `-v`
   would have produced a fresh keystore against an existing database and
   crashed with `No such alias`. Fixed in `certify/docker-compose`.

2. **The key seed script ran against the wrong database.** `certify_init.sql`
   does `CREATE DATABASE inji_certify` then `\c inji_certify`, but every
   Postgres init script gets a fresh connection, so the seed landed on the
   default `postgres` database and failed with
   `relation "certify.key_alias" does not exist`. It failed silently — the
   container still reported healthy and Certify simply generated its own key.
   Fixed by adding `\c inji_certify postgres` to the top of the seed file.
   Worth adding to the issuer setup instructions.

## Interoperability findings (FR15 candidates)

1. **Mimoto 0.22.0 rejects `mso_mdoc`** — Certify issues ISO 18013-5 mDoc
   credentials, Inji Web cannot accept them
   (`Unsupported credential format: mso_mdoc`). MOSIP ships
   `IGNORED_ISSUER_IDS=MockMdl` in their own compose for this reason.

2. **`did:web` issuer identity breaks across instances** — the signing key is
   per-instance but the DID document is global, so only one developer's Certify
   can match what is published. Needs a seeded shared key or self-hosted DID
   resolution. Cost several hours before it was diagnosed.

## Not done yet

- **FR4 — presentation and verification.** Not started. Open question: whether
  Inji Web supports OpenID4VP presentation at all, or whether the mobile wallet
  is required for it.
- **Protocol payload capture for FR5.** The inspector needs the wallet's half
  of each exchange; the capture approach has not been agreed with whoever owns
  the BFF.
- **Headless holder.** A real wallet needs a human to approve, so the automated
  matrix (FR7, FR14) cannot drive it. A programmable holder is needed, and it
  doubles as the non-Inji mock for FR8. This is the largest remaining piece.

## Local files not in the repo

Three files are required locally and are gitignored. Anyone setting this up
needs to recreate them — see `wallet/README.md`:

- `wallet/docker-compose/.env` — Google OAuth credentials
- `wallet/docker-compose/certs/oidckeystore.p12` — OIDC client keystore
- `certify/docker-compose/keys_seed.local.sql` and `data/CERTIFY_PKCS12/local.p12`
  — the shared issuer signing key

## Try it

```bash
docker network create mosip_network
cd certify/docker-compose && docker compose up -d
cd ../../wallet/docker-compose && docker compose up -d
```

Open `http://localhost:3004`. Mock identity `2154189532`, OTP `111111`.
