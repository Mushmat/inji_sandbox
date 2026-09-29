-- Let Inji Web (Mimoto 0.22) bind Farmer credentials to its Ed25519 wallet key, the key it always signs
-- presentations with (FINDINGS W3/W4). Mimoto only knows the name "Ed25519"; RFC 8037 wallets say "EdDSA".
-- For a running Certify: psql -U postgres -d inji_certify -f this file, then restart Certify.
-- For certify_init.sql: put the same lists in the proof_types_supported values of both Farmer inserts.
UPDATE certify.credential_config
   SET proof_types_supported = '{"jwt": {"proof_signing_alg_values_supported": ["RS256", "ES256", "EdDSA", "Ed25519"]}}'::jsonb
 WHERE credential_format = 'ldp_vc';
UPDATE certify.credential_config
   SET proof_types_supported = '{"jwt": {"proof_signing_alg_values_supported": ["RS256", "PS256", "ES256", "EdDSA", "Ed25519"]}}'::jsonb
 WHERE credential_format = 'vc+sd-jwt';
