"""
The playground's own checks on a presentation, run next to Inji Verify's.

Inji Verify's answer is the result under test. These checks are the
reference it is compared with: if Inji Verify says VALID while one of these
fails, that is a suspected gap worth a closer look (and possibly an issue
upstream). Every check says which spec rule it comes from.

Each check is {id, label, ok, detail, ref}; ok is True, False, or None when
it could not be run (missing input, DID document unreachable, ...).
"""
import base64
import hashlib
import json
import os
import time
from datetime import datetime, timezone

import requests

import pex
import sdjwt
from did_resolver import (default_fetch_json, did_document_keys, did_web_overrides, did_web_url, jwk_of_did,
                          jwk_to_public_key, public_key_to_jwk, resolve_key, same_key)
from jsonld_proofs import b64url, verify_ed25519_2020, verify_jws2020

CERTIFY_ISSUER_ID = os.environ.get("CERTIFY_ISSUER_ID", "http://certify-nginx:80")
CERTIFY_DID_DOCUMENT_URL = os.environ.get("CERTIFY_DID_DOCUMENT_URL", "http://localhost:8090/v1/certify/.well-known/did.json")
KB_MAX_AGE_SECONDS = 300

REF = {
    "vp": "OpenID4VP (draft 21-23) §6, W3C VC Data Model 1.1 §4.10",
    "pe": "DIF Presentation Exchange 2.0 §5 / §6",
    "ldp": "W3C VC Data Integrity; JsonWebSignature2020 / Ed25519Signature2020 suites",
    "sdjwt": "IETF SD-JWT (draft 13+) §4, §8",
    "sdjwtvc": "IETF SD-JWT VC",
    "vcdm": "W3C VC Data Model 1.1 §4.8 (expirationDate)",
}


def _check(cid, label, ok, detail=None, ref=None):
    return {"id": cid, "label": label, "ok": ok, "detail": detail, "ref": ref}


def _parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# ----------------------------------------------------------------- common

def check_submission(session, submitted, vc_format):
    out = []
    state_ok = submitted.get("state") == session.get("request_id")
    out.append(_check("state", "Response state is this session's request id", state_ok,
                      None if state_ok else f"state {submitted.get('state')!r}, session {session.get('request_id')!r}", REF["vp"]))
    ps = submitted.get("presentation_submission") or {}
    pd = session.get("presentation_definition") or {}
    desc_ids = {d.get("id") for d in pd.get("input_descriptors", [])}
    ok = ps.get("definition_id") == pd.get("id") and all(m.get("id") in desc_ids for m in ps.get("descriptor_map", [])) and ps.get("descriptor_map")
    out.append(_check("submission", "presentation_submission points at this request's definition", bool(ok),
                      None if ok else f"definition_id {ps.get('definition_id')!r} vs {pd.get('id')!r}; "
                                      f"descriptor ids {[m.get('id') for m in ps.get('descriptor_map', [])]} vs {sorted(desc_ids)}", REF["pe"]))
    return out


def check_constraints(session, view, vc_format):
    pd = session.get("presentation_definition") or {}
    descriptors = pd.get("input_descriptors") or []
    failures_by_desc = [(d.get("id"), pex.constraint_failures(d, view)) for d in descriptors]
    ok = any(not f for _, f in failures_by_desc) if descriptors else None
    detail = None
    if ok is False:
        detail = "; ".join(f"{did}: {', '.join(f)}" for did, f in failures_by_desc)
    return [_check("constraints", "Credential meets the presentation_definition constraints", ok, detail, REF["pe"])]


def check_did_document_current(issuer_did, fetch_json=default_fetch_json):
    """Is the DID document a verifier downloads the one Certify signs with right now?"""
    if not issuer_did or not issuer_did.startswith("did:web:"):
        return []
    try:
        local = fetch_json(CERTIFY_DID_DOCUMENT_URL)
    except Exception:
        return []  # Certify not reachable from here: nothing to compare
    if local.get("id") != issuer_did:
        return []
    url = did_web_overrides().get(issuer_did) or did_web_url(issuer_did)
    try:
        published = fetch_json(url)
    except Exception as e:
        return [_check("did_published", "Issuer DID document is published", False,
                       f"{url}: {e}. Verifiers (Inji Verify included) cannot check Certify's signature until did.json "
                       "is hosted there (certify/README.md, 'DID hosting').", "did:web method spec")]
    a, b = did_document_keys(local), did_document_keys(published)
    ok = bool(a) and all(any(same_key(k, pk) for pk in b.values()) for k in a.values())
    return [_check("did_published", "Published DID document has Certify's current keys", ok,
                   None if ok else f"Certify's keys ({CERTIFY_DID_DOCUMENT_URL}) are not all in {url}. "
                   "Each fresh Certify database generates new keys, so the hosted did.json must be updated "
                   "after a reset, or every verifier will reject the issuer signature.", "did:web method spec")]


def x5c_public_key(cert_b64: str):
    from cryptography import x509
    return x509.load_der_x509_certificate(base64.b64decode(cert_b64)).public_key()


def _known_issuer_keys(iss, fetch_json):
    """Public JWKs the issuer is known to use, and where they came from."""
    if iss and iss.startswith("did:"):
        if iss.startswith("did:web:"):
            url = did_web_overrides().get(iss) or did_web_url(iss)
            return list(did_document_keys(fetch_json(url)).values()), url
        jwk = jwk_of_did(iss)
        return ([jwk] if jwk else []), iss
    if iss and iss.rstrip("/") == CERTIFY_ISSUER_ID.rstrip("/"):
        # Certify's SD-JWT iss is its domain URL, only resolvable inside Docker;
        # its keys are the ones in its DID document.
        return list(did_document_keys(fetch_json(CERTIFY_DID_DOCUMENT_URL)).values()), CERTIFY_DID_DOCUMENT_URL
    meta = fetch_json(iss.rstrip("/") + "/.well-known/jwt-vc-issuer")
    jwks = meta.get("jwks") or fetch_json(meta["jwks_uri"])
    return jwks.get("keys", []), iss.rstrip("/") + "/.well-known/jwt-vc-issuer"


def check_key_belongs_to_issuer(iss, key, fetch_json=default_fetch_json):
    label = "Signing key belongs to the issuer"
    ref = "IETF SD-JWT VC §3.5 (issuer key via iss metadata, DID, or a trusted x5c chain)"
    try:
        keys, source = _known_issuer_keys(iss, fetch_json)
    except Exception as e:
        return _check("issuer_key_binding", label, None, f"could not look up the keys of issuer {iss}: {e}", ref)
    ok = any(same_key(public_key_to_jwk(key), k) for k in keys)
    return _check("issuer_key_binding", label, ok,
                  None if ok else f"the SD-JWT is signed by a key that is not one of {iss}'s keys ({source}). "
                  "A self-signed x5c proves nothing about who issued it.", ref)


# --------------------------------------------------------------- JSON-LD

def check_ldp_presentation(session, vp, fetch_json=default_fetch_json):
    out = []
    proof = vp.get("proof") or {}
    holder = vp.get("holder")
    vm = proof.get("verificationMethod", "")
    try:
        key, _ = resolve_key(vm, fetch_json)
        ok = verify_jws2020(vp, key) if proof.get("type") == "JsonWebSignature2020" else None
        detail = None if ok else (f"proof type {proof.get('type')} not checked here" if ok is None else "signature does not verify")
    except Exception as e:
        ok, detail = None, f"could not resolve {vm}: {e}"
    out.append(_check("holder_signature", "Holder's signature on the presentation", ok, detail, REF["ldp"]))

    ok = proof.get("challenge") == session.get("nonce")
    out.append(_check("challenge", "proof.challenge is this session's nonce", ok,
                      None if ok else f"challenge {proof.get('challenge')!r}, session nonce {session.get('nonce')!r} (replayed presentation?)", REF["vp"]))
    ok = proof.get("domain") == session.get("client_id")
    out.append(_check("domain", "proof.domain is this verifier's client_id", ok,
                      None if ok else f"domain {proof.get('domain')!r}, client_id {session.get('client_id')!r}", REF["vp"]))

    creds = vp.get("verifiableCredential") or []
    creds = creds if isinstance(creds, list) else [creds]
    vm_did = vm.split("#")[0]
    for vc in creds:
        subject = vc.get("credentialSubject") or {}
        subject = subject[0] if isinstance(subject, list) and subject else subject
        sid = subject.get("id") if isinstance(subject, dict) else None
        ok = bool(sid) and same_key(jwk_of_did(sid), jwk_of_did(vm_did)) and (holder is None or same_key(jwk_of_did(holder), jwk_of_did(sid)))
        out.append(_check("holder_binding", "Presenter is the credential's subject (holder binding)", ok,
                          None if ok else f"credentialSubject.id {str(sid)[:60]}..., presentation signed by {vm_did[:60]}...", REF["vp"]))
        out += check_ldp_credential(session, vc, fetch_json)
    return out


def check_ldp_credential(session, vc, fetch_json=default_fetch_json):
    out = []
    proof = vc.get("proof") or {}
    vm = proof.get("verificationMethod", "")
    try:
        key, info = resolve_key(vm, fetch_json)
        if proof.get("type") == "Ed25519Signature2020":
            ok = verify_ed25519_2020(vc, key)
        elif proof.get("type") == "JsonWebSignature2020":
            ok = verify_jws2020(vc, key)
        else:
            ok = None
        detail = (f"key from {info.get('fetched_from', info['method'])}" if ok else
                  "signature does not verify: the credential was changed after issuance, or the DID document has other keys"
                  if ok is False else f"proof type {proof.get('type')} not checked here")
    except Exception as e:
        ok, detail = None, f"could not resolve issuer key {vm}: {e}"
    out.append(_check("issuer_signature", "Issuer's signature on the credential", ok, detail, REF["ldp"]))
    issuer = vc.get("issuer") if isinstance(vc.get("issuer"), str) else (vc.get("issuer") or {}).get("id")
    vm_did = vm.split("#")[0]
    bound = vm_did == issuer
    out.append(_check("issuer_key_binding", "Signing key belongs to the issuer", bound,
                      None if bound else f"signed with a key of {vm_did[:60]}, but the credential claims issuer {issuer}. "
                      "Anyone can sign with their own key; the verification method must be the issuer's.",
                      "W3C VC Data Integrity (verification method controlled by the issuer)"))
    if ok is False:
        out += check_did_document_current(issuer, fetch_json)
    exp = _parse_time(vc.get("expirationDate") or vc.get("validUntil"))
    ok = None if exp is None else exp > datetime.now(timezone.utc)
    out.append(_check("expiry", "Credential has not expired", ok if exp else True,
                      "no expirationDate" if exp is None else (None if ok else f"expired {vc.get('expirationDate') or vc.get('validUntil')}"), REF["vcdm"]))
    out += check_constraints(session, vc, "ldp_vc")
    return out


# ----------------------------------------------------------------- SD-JWT

def check_sd_jwt(session, token, fetch_json=default_fetch_json, require_kb=True):
    out = []
    try:
        p = sdjwt.parse(token)
    except Exception as e:
        return [_check("sd_jwt_parse", "Presentation is a well-formed SD-JWT", False, str(e), REF["sdjwt"])]
    header, payload = p["header"], p["payload"]

    key = None
    if header.get("x5c"):
        # Certify sends its SD-JWT signing certificate in x5c; that is also the only
        # place Inji Verify 0.18.2 takes the key from.
        try:
            key = x5c_public_key(header["x5c"][0])
            ok = sdjwt.verify_jws(p["jwt"], key)
            detail = "key from the x5c certificate in the header" if ok else "signature does not verify against the x5c certificate"
        except Exception as e:
            ok, detail = None, f"could not read the x5c certificate: {e}"
    else:
        ref = header.get("kid") if str(header.get("kid", "")).startswith("did:") else payload.get("iss", "")
        try:
            key, info = resolve_key(ref, fetch_json, alg=header.get("alg"))
            ok = sdjwt.verify_jws(p["jwt"], key)
            detail = f"key from {info.get('fetched_from', info['method'])}" if ok else "signature does not verify"
        except Exception as e:
            ok, detail = None, f"could not resolve issuer key {ref}: {e}"
    out.append(_check("issuer_signature", "Issuer's signature on the SD-JWT", ok, detail, REF["sdjwt"]))
    if key is not None and ok:
        out.append(check_key_belongs_to_issuer(payload.get("iss"), key, fetch_json))
    if ok is False:
        out += check_did_document_current(payload.get("iss"), fetch_json)

    view, unmatched, _ = sdjwt.reconstruct(payload, p["disclosures"])
    ok = not unmatched
    out.append(_check("disclosures", "Every disclosure matches a digest the issuer signed", ok,
                      None if ok else f"{len(unmatched)} disclosure(s) match no _sd digest: "
                      + ", ".join(f"{d['name']}={json.dumps(d['value'])[:40]}" for d in unmatched), REF["sdjwt"]))

    kb = p["kb_jwt"]
    if not kb:
        out.append(_check("kb_present", "Key-binding JWT is present", False if require_kb else None,
                          "no KB-JWT: anyone holding a copy could present this", REF["sdjwt"]))
    else:
        kb_header, kb_payload = sdjwt.decode_jwt_part(kb.split(".")[0]), sdjwt.decode_jwt_part(kb.split(".")[1])
        cnf = payload.get("cnf") or {}
        holder_jwk = cnf.get("jwk") or jwk_of_did(cnf.get("kid"))
        if holder_jwk:
            ok = kb_header.get("typ") == "kb+jwt" and sdjwt.verify_jws(kb, jwk_to_public_key(holder_jwk))
            detail = None if ok else f"typ {kb_header.get('typ')!r}; signature by the cnf key fails"
        else:
            ok, detail = None, "credential has no cnf key to check against"
        out.append(_check("kb_signature", "Key-binding JWT is signed by the credential's holder key", ok, detail, REF["sdjwt"]))
        ok = kb_payload.get("nonce") == session.get("nonce")
        out.append(_check("kb_nonce", "KB-JWT nonce is this session's nonce", ok,
                          None if ok else f"nonce {kb_payload.get('nonce')!r}, session {session.get('nonce')!r} (replayed presentation?)", REF["sdjwt"]))
        ok = kb_payload.get("aud") == session.get("client_id")
        out.append(_check("kb_aud", "KB-JWT aud is this verifier's client_id", ok,
                          None if ok else f"aud {kb_payload.get('aud')!r}, client_id {session.get('client_id')!r}", REF["sdjwt"]))
        expected = b64url(hashlib.sha256(p["presented_part"].encode("ascii")).digest())
        ok = kb_payload.get("sd_hash") == expected
        out.append(_check("kb_sd_hash", "KB-JWT sd_hash covers exactly what was presented", ok,
                          None if ok else "sd_hash does not match the presented SD-JWT and disclosures", REF["sdjwt"]))
        age = time.time() - kb_payload.get("iat", 0)
        ok = -60 <= age <= KB_MAX_AGE_SECONDS
        out.append(_check("kb_fresh", f"KB-JWT was made in the last {KB_MAX_AGE_SECONDS // 60} minutes", ok,
                          None if ok else f"iat is {int(age)} s old", REF["sdjwt"]))

    exp = payload.get("exp")
    ok = exp is None or exp > time.time()
    out.append(_check("expiry", "Credential has not expired", ok, None if ok else f"exp {exp}", REF["sdjwtvc"]))
    out += check_constraints(session, view, "vc+sd-jwt")
    return out


# ---------------------------------------------------------------- entry

def run_checks(vc_format, session, submitted=None, verifier_credentials=None, fetch_json=default_fetch_json):
    """submitted: {vp_token, presentation_submission, state} as the wallet sent it
    (built-in wallet). Phone mode has no copy of the presentation, so only the
    credential(s) Inji Verify returns are checked (verifier_credentials)."""
    out = []
    if submitted:
        out += check_submission(session, submitted, vc_format)
        token = submitted["vp_token"]
        if vc_format == "ldp_vc":
            out += check_ldp_presentation(session, token if isinstance(token, dict) else json.loads(token), fetch_json)
        else:
            out += check_sd_jwt(session, token, fetch_json)
    else:
        for c in verifier_credentials or []:
            if isinstance(c, str) and c.lstrip().startswith("{"):
                c = json.loads(c)
            if isinstance(c, dict):
                out += check_ldp_credential(session, c, fetch_json)
            elif isinstance(c, str):
                out += check_sd_jwt(session, c, fetch_json)
        if not verifier_credentials:
            out.append(_check("no_copy", "Independent checks", None,
                              "no copy of the presentation to check (the verifier returned no credentials)", None))
    return out
