"""What can play each role, and which combinations can actually run.

A combination the stack can't support is still listed, with the reason, so the
matrix shows the gap instead of hiding it. The finding IDs point at
verify/docs/FINDINGS.md and wallet/README.md.
"""

from config import PLAYGROUND_PUBLIC_URL, VERSIONS

FORMATS = {
    "ldp_vc": {"label": "W3C VC (JSON-LD)", "short": "JSON-LD", "spec": "W3C VC Data Model 1.1, Ed25519Signature2020"},
    "vc+sd-jwt": {"label": "SD-JWT VC", "short": "SD-JWT", "spec": "IETF SD-JWT VC, selective disclosure of farmerID"},
    "mso_mdoc": {"label": "mDoc / mDL", "short": "mDoc", "spec": "ISO/IEC 18013-5, CBOR + COSE_Sign1"},
}

ISSUERS = {
    "certify_preauth": {
        "name": "Inji Certify · pre-authorized",
        "inji": True,
        "version": VERSIONS.get("Inji Certify"),
        "protocol": "OpenID4VCI draft 13, pre-authorized code",
        "detail": "Certify writes the credential offer and is its own authorization server. The person's details "
                  "travel with the offer, so edits apply straight away. Signs as did:web:mushmat.github.io:inji_sandbox.",
        "formats": ["ldp_vc", "vc+sd-jwt"],
    },
    "certify": {
        "name": "Inji Certify · eSignet login",
        "inji": True,
        "version": VERSIONS.get("Inji Certify"),
        "protocol": "OpenID4VCI draft 13, authorization code",
        "detail": "The same Certify and keys, with the holder logging in through MOSIP Collab's mock eSignet. "
                  "The path Inji Web uses. New details need a Certify restart to load.",
        "formats": ["ldp_vc", "vc+sd-jwt", "mso_mdoc"],
    },
    "test_issuer": {
        "name": "Test issuer",
        "inji": False,
        "version": None,
        "protocol": "Direct issuance (no OpenID4VCI)",
        "detail": "A local did:key issuer that signs the same Farmer credential shapes with a standard library. "
                  "Shows Inji Verify handling credentials from an issuer it has never seen.",
        "formats": ["ldp_vc", "vc+sd-jwt"],
    },
}

WALLETS = {
    "playground_wallet": {
        "name": "Playground wallet",
        "inji": False,
        "version": None,
        "protocol": "OpenID4VCI + OpenID4VP direct_post",
        "detail": "A scripted holder with its own EC P-256 key. Runs unattended and exposes every message it sends, "
                  "so it can also misbehave on purpose for the tamper scenarios.",
        "interactive": False,
        "receive": ["ldp_vc", "vc+sd-jwt", "mso_mdoc"],
        "present": ["ldp_vc", "vc+sd-jwt"],
    },
    "inji_web": {
        "name": "Inji Web",
        "inji": True,
        "version": " + ".join(f"{k} {v}" for k, v in VERSIONS.items() if k in ("Inji Web", "Mimoto")),
        "protocol": "OpenID4VCI + OpenID4VP (via Mimoto)",
        "detail": "MOSIP's browser wallet. You download the card and approve the presentation yourself, "
                  "so the Playground sees what the issuer and verifier see, not Mimoto's internals.",
        "interactive": True,
        "receive": ["ldp_vc", "vc+sd-jwt"],
        "present": ["ldp_vc"],
    },
    "browser_wallet": {
        "name": "Wallet on this device",
        "inji": False,
        "version": None,
        "protocol": "OpenID4VP over the Digital Credentials API",
        "detail": "The browser asks the wallets on this device, or a phone paired with it, through "
                  "navigator.credentials.get. Needs a browser and wallet that support the API.",
        "interactive": True,
        "receive": [],
        "present": ["ldp_vc", "vc+sd-jwt"],
        "brings_own_credential": True,
    },
}

VERIFIERS = {
    "inji_verify": {
        "name": "Inji Verify",
        "inji": True,
        "version": VERSIONS.get("Inji Verify"),
        "protocol": "OpenID4VP draft 21-23, direct_post",
        "detail": "verify-service behind an https tunnel. The Playground acts as the relying party and "
                  "re-checks every result independently.",
        "formats": ["ldp_vc", "vc+sd-jwt"],
    },
    "playground_verifier": {
        "name": "Playground verifier",
        "inji": False,
        "version": None,
        "protocol": "OpenID4VP draft 21-23, direct_post",
        "detail": "Our own relying party, written from the specs. Checks the holder's nonce, the presentation_definition "
                  "and that the signing key is the issuer's, for both formats.",
        "formats": ["ldp_vc", "vc+sd-jwt"],
    },
}

SCENARIOS = {
    "none": {"label": "Honest", "expected": "VALID", "tamper": False},
    "altered": {"label": "Altered claim", "expected": "INVALID", "tamper": True},
    "replay": {"label": "Replayed presentation", "expected": "INVALID", "tamper": True},
    "wrong_type": {"label": "Wrong credential type", "expected": "INVALID", "tamper": True},
    "forged_issuer": {"label": "Forged issuer", "expected": "INVALID", "tamper": True},
    "expired": {"label": "Expired credential", "expected": "EXPIRED", "tamper": True},
}


def check(issuer: str, wallet: str, verifier: str, fmt: str, scenario: str) -> dict:
    """blockers stop the run; limits let it run and are recorded as the expected gap."""
    blockers, limits = [], []
    i, w, v = ISSUERS.get(issuer), WALLETS.get(wallet), VERIFIERS.get(verifier)
    if not (i and w and v and fmt in FORMATS and scenario in SCENARIOS):
        return {"runnable": False, "blockers": ["Unknown issuer, wallet, verifier, format or scenario."], "limits": []}

    if w.get("brings_own_credential"):
        return _check_browser_wallet(verifier, fmt, scenario)
    if fmt not in i["formats"]:
        blockers.append(f"{i['name']} doesn't issue {FORMATS[fmt]['short']}.")
    if fmt not in w["receive"]:
        blockers.append(f"{w['name']} can't store {FORMATS[fmt]['short']} credentials"
                        + (" (Mimoto 0.22 rejects mso_mdoc, see wallet/README.md)." if wallet == "inji_web" else "."))
    if wallet == "inji_web" and issuer == "test_issuer":
        blockers.append("Inji Web only downloads from issuers in its mimoto-issuers-config.json; the test issuer has no "
                        "OpenID4VCI endpoint to add there.")
    if wallet == "inji_web" and issuer == "certify_preauth":
        blockers.append("Our Inji Web is set up to download from its issuer list with an eSignet login. "
                        "Pick Inji Certify · eSignet login for Inji Web runs.")
    if wallet == "inji_web" and verifier == "playground_verifier" and not PLAYGROUND_PUBLIC_URL.startswith("https://"):
        blockers.append("Inji Web only answers verifiers on an https address without a port (FINDINGS W2). "
                        "Start the stack with integration/stack.py so the Playground verifier gets its tunnel.")
    if wallet == "inji_web" and scenario not in ("none", "wrong_type"):
        blockers.append("Tamper scenarios need a wallet that misbehaves on purpose. Use the Playground wallet.")
    if scenario in ("forged_issuer", "expired") and issuer in ("certify", "certify_preauth"):
        limits.append("Certify won't sign a forged or already-expired credential, so this scenario presents one "
                      "made by the test issuer after issuing from Certify.")

    if not blockers:
        if fmt not in w["present"]:
            reason = "Inji Web can't present SD-JWT over OpenID4VP (FINDINGS W5)." if wallet == "inji_web" \
                else f"{w['name']} can't present {FORMATS[fmt]['short']}."
            limits.append(reason)
        if fmt not in v["formats"]:
            limits.append(f"{v['name']} can't receive {FORMATS[fmt]['short']} over OpenID4VP (FINDINGS M1). "
                          "Issuance runs; presentation is recorded as unsupported.")
    return {"runnable": not blockers, "blockers": blockers, "limits": limits}


def _check_browser_wallet(verifier: str, fmt: str, scenario: str) -> dict:
    blockers = []
    if verifier != "playground_verifier":
        blockers.append("In this setup only the Playground verifier takes Digital Credentials API answers.")
    if fmt not in WALLETS["browser_wallet"]["present"]:
        blockers.append(f"The Playground verifier asks for JSON-LD or SD-JWT over the API, not {FORMATS[fmt]['short']}.")
    if scenario != "none":
        blockers.append("Tamper scenarios need a wallet that misbehaves on purpose. Use the Playground wallet.")
    limits = ["The Playground can't issue into a wallet it doesn't control, so the issuer choice doesn't apply: "
              "the wallet presents a Farmer credential it already holds."]
    return {"runnable": not blockers, "blockers": blockers, "limits": limits}


def catalog() -> dict:
    return {"issuers": ISSUERS, "wallets": WALLETS, "verifiers": VERIFIERS,
            "formats": FORMATS, "scenarios": SCENARIOS, "versions": VERSIONS}
