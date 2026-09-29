#!/usr/bin/env python3
"""
CLI for the Present & Verify flow (the verify/ counterpart of Chirayu's
test_issuance_flow.py).

Usage:
    pip install -r requirements.txt
    python3 test_presentation_flow.py ldp_vc                  # honest presentation
    python3 test_presentation_flow.py "vc+sd-jwt" replay       # a negative test
    python3 test_presentation_flow.py ldp_vc all               # every scenario, summary table
    python3 test_presentation_flow.py ldp_vc none --source certify   # fetch a fresh credential first
    python3 test_presentation_flow.py ldp_vc none --source test      # offline test issuer (no Certify)

Scenarios: none, altered, replay, wrong_type (see presentation_flow.py).
Sources:   wallet (default when the wallet already holds one), certify, test.
Exit code: 0 when every run's verdict is PASS, 1 otherwise.
"""
import argparse
import json
import sys

from presentation_flow import SCENARIOS, SOURCES, run_presentation

MARK = {True: "ok ", False: "FAIL", None: " -- "}


def show(result, verbose):
    print(f"\n######## {result['format']} / {result['scenario']}: {SCENARIOS.get(result['scenario'], {}).get('label', '')}")
    for i, s in enumerate(result["steps"], 1):
        status = s["status"] if s["status"] is not None else s["method"]
        print(f"  {i:2}. [{s.get('actor', ''):10}] {s['name']}  ({status}{'' if s['ok'] else ', NOT OK'})")
        if verbose and s.get("response") is not None:
            print("      " + json.dumps(s["response"], indent=2)[:1500].replace("\n", "\n      "))
    if not result["ok"]:
        print("\n  FAILED:", result["error"])
        return
    v = result["verifier_result"]
    print(f"\n  Inji Verify: {v['status']}" + (f"  ({v['detail']})" if v.get("detail") else ""))
    for c in v.get("checks", []):
        print(f"    {MARK[c['ok']]} {c['label']}" + (f": {c['detail']}" if c.get("detail") else ""))
    print("  Playground checks:")
    for c in result["playground_checks"]:
        print(f"    {MARK[c['ok']]} {c['label']}" + (f": {c['detail']}" if c.get("detail") and c["ok"] is not True else ""))
    o = result["outcome"]
    print(f"\n  expected {o['expected']}, Inji Verify said {o['result']}  ->  {o['verdict']}")
    for g in result["suspected_gaps"]:
        print(f"  SUSPECTED GAP{' (' + ', '.join(g['finding']) + ')' if g.get('finding') else ''}: {g['summary']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("format", nargs="?", default="ldp_vc", help="ldp_vc | vc+sd-jwt | mso_mdoc")
    ap.add_argument("scenario", nargs="?", default="none", help=" | ".join(list(SCENARIOS) + ["all"]))
    ap.add_argument("--source", choices=SOURCES, default=None)
    ap.add_argument("-v", "--verbose", action="store_true", help="print every response body")
    ap.add_argument("--json", action="store_true", help="print the raw result as JSON")
    args = ap.parse_args()

    scenarios = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    results = []
    for i, sc in enumerate(scenarios):
        # fetch from Certify at most once, then reuse what the wallet holds
        source = args.source if i == 0 else ("wallet" if args.source == "certify" else args.source)
        r = run_presentation(args.format, sc, source=source)
        results.append(r)
        print(json.dumps(r, indent=2, default=str)) if args.json else show(r, args.verbose)

    if len(results) > 1:
        print("\n  scenario      expected  Inji Verify  verdict")
        for r in results:
            o = r.get("outcome") or {}
            print(f"  {r['scenario']:12}  {o.get('expected', '-'):8}  {o.get('result', 'error'):11}  {o.get('verdict', 'ERROR')}")
    sys.exit(0 if all(r.get("outcome", {}).get("verdict") == "PASS" for r in results) else 1)


if __name__ == "__main__":
    main()
