"""
Presentation definitions (DIF Presentation Exchange v2) as Inji Verify 0.18.2
can carry them, plus the matching logic a wallet/verifier needs.

Inji Verify's PD model (VPDefinitionResponseDto / FieldDTO / FilterDTO) keeps
only path, filter.type and filter.pattern, drops limit_disclosure, and its
top-level `format` only knows jwt / jwt_vc / ldp_vc. So filters use `pattern`
and the format goes on each input descriptor.
"""
import json
import re
import uuid

FARMER_TYPE = "FarmerCredential"
FARMER_VCT = "FarmerCredentialSdJwt"          # vct of Chirayu's SD-JWT config
WRONG_TYPE = "LandOwnershipCredential"          # used by the "wrong type" tamper test
WRONG_VCT = "LandOwnershipCredentialSdJwt"
PURPOSE = "Confirm the holder is a registered farmer"


def build_presentation_definition(vc_format: str, credential_type: str = FARMER_TYPE, fields=("farmerID",)) -> dict:
    wrong = credential_type != FARMER_TYPE
    if vc_format == "ldp_vc":
        descriptor = {
            "id": "farmer-credential",
            "format": {"ldp_vc": {"proof_type": ["Ed25519Signature2020"]}},
            "constraints": {"fields": [{"path": ["$.type"], "filter": {"type": "object", "pattern": credential_type}}]},
        }
    elif vc_format == "vc+sd-jwt":
        descriptor = {
            "id": "farmer-credential",
            "format": {"vc+sd-jwt": {"sd-jwt_alg_values": ["EdDSA", "ES256", "RS256"], "kb-jwt_alg_values": ["ES256", "EdDSA", "RS256"]}},
            "constraints": {"fields": [{"path": ["$.vct"], "filter": {"type": "string", "pattern": WRONG_VCT if wrong else FARMER_VCT}}]
                            + [{"path": [f"$.credentialSubject.{f}"]} for f in fields]},
        }
    else:
        raise ValueError(f"presentation over OpenID4VP is not supported for {vc_format} by Inji Verify 0.18.2")
    return {"id": str(uuid.uuid4()), "purpose": PURPOSE, "input_descriptors": [descriptor]}


def eval_path(obj, path: str):
    """Tiny JSONPath: $.a.b, $.a[0], $['a']. Returns (found, value)."""
    if not path.startswith("$"):
        return False, None
    cur = obj
    for tok in re.findall(r"\.([^.\[\]]+)|\[(\d+)\]|\['([^']+)'\]", path[1:]):
        key = tok[0] or tok[2] or (int(tok[1]) if tok[1] else None)
        try:
            cur = cur[key]
        except (KeyError, IndexError, TypeError):
            return False, None
    return True, cur


def filter_matches(value, flt) -> bool:
    if not flt:
        return True
    if "const" in flt:
        return flt["const"] in value if isinstance(value, list) else value == flt["const"]
    if "enum" in flt:
        return value in flt["enum"]
    if isinstance(flt.get("contains"), dict) and "const" in flt["contains"]:
        return isinstance(value, list) and flt["contains"]["const"] in value
    if "pattern" in flt:
        rx = re.compile(flt["pattern"])
        if isinstance(value, list):
            return any(rx.search(str(v)) for v in value)
        return bool(rx.search(value if isinstance(value, str) else json.dumps(value)))
    return True


def constraint_failures(descriptor: dict, view: dict) -> list:
    out = []
    for field in (descriptor or {}).get("constraints", {}).get("fields", []):
        if field.get("optional"):
            continue
        hit = None
        for p in field["path"]:
            found, value = eval_path(view, p)
            if found:
                hit = (p, value)
                break
        if hit is None:
            out.append(f"{' | '.join(field['path'])} is missing")
        elif not filter_matches(hit[1], field.get("filter")):
            out.append(f"{hit[0]} = {json.dumps(hit[1])[:80]} does not match {json.dumps(field.get('filter'))}")
    return out


def referenced_claims(descriptor: dict) -> set:
    names = set()
    for field in (descriptor or {}).get("constraints", {}).get("fields", []):
        for p in field["path"]:
            m = re.match(r"^\$\.(?:credentialSubject\.)?([A-Za-z0-9_]+)$", p)
            if m and m.group(1) not in ("vct", "type", "iss", "cnf"):
                names.add(m.group(1))
    return names


def accepted_formats(pd: dict, descriptor: dict, client_metadata: dict = None) -> list:
    fmt = (descriptor or {}).get("format") or (pd or {}).get("format") or (client_metadata or {}).get("vp_formats") or {}
    return list(fmt.keys())
