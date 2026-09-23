#!/usr/bin/env python3
"""
CLI smoke test for the issuance flow in issuance_flow.py.

Usage:
    pip install -r requirements.txt
    python3 test_issuance_flow.py ldp_vc        # JSON-LD Farmer Credential
    python3 test_issuance_flow.py "vc+sd-jwt"   # SD-JWT Farmer Credential
"""
import json
import sys

from issuance_flow import run_issuance


def main():
    vc_format = sys.argv[1] if len(sys.argv) > 1 else "ldp_vc"
    result = run_issuance(vc_format)

    for i, step in enumerate(result["steps"], 1):
        print(f"\n=== {i}. {step['name']} === status={step['status']}")

    if not result["ok"]:
        print("\nFAILED:", result["error"])
        print(json.dumps(result["steps"][-1].get("response"), indent=2))
        sys.exit(1)

    print("\ncredential:")
    print(json.dumps(result["credential"], indent=2) if isinstance(result["credential"], dict)
          else result["credential"])

    if result["credential_decoded"]:
        print("\ndecoded SD-JWT payload:")
        print(json.dumps(result["credential_decoded"]["payload"], indent=2))
        print("\ndisclosures:")
        print(json.dumps(result["credential_decoded"]["disclosures"], indent=2))

    sys.exit(0)


if __name__ == "__main__":
    main()
