"""Runs the test matrix against a running Playground and writes the report. CI-style (FR14).

    python playground/run_matrix.py              # quick: every issuer, verifier and format, honest runs
    python playground/run_matrix.py --full       # plus every tamper scenario
    python playground/run_matrix.py --out report.md --url http://localhost:5050 --strict

Exits 1 if any run ends in ERROR (something broke), and with --strict also on FAIL (a verifier gave
the wrong answer; today that is Inji Verify's known gaps F2, F3 and F10). Standard library only.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def call(base, path, body=None):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read().decode()
        return json.loads(text) if r.headers.get("content-type", "").startswith("application/json") else text


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default="http://localhost:5050")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--out", default="interoperability-report.md")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--wait", type=int, default=900, help="seconds to wait for the Playground to come up")
    args = ap.parse_args()
    base = args.url.rstrip("/")

    deadline = time.time() + args.wait
    while True:
        try:
            health = call(base, "/api/health")
            break
        except (urllib.error.URLError, OSError):
            if time.time() > deadline:
                sys.exit(f"The Playground at {base} didn't answer within {args.wait} s.")
            time.sleep(5)
    if not health["did"]["ok"]:
        print("WARNING:", health["did"]["detail"])
    down = [s["label"] for s in health["services"] if not s["up"] and s["id"] not in ("mimoto", "inji_web")]
    if down:
        print("Not up yet, runs that need them will error:", ", ".join(down))

    state = call(base, "/api/matrix", {"preset": "full" if args.full else "quick"})
    print(f"Running {state['total']} combinations...")
    seen = 0
    while state["running"]:
        time.sleep(3)
        state = call(base, "/api/matrix")
        if state["done"] != seen:
            seen = state["done"]
            print(f"  {seen}/{state['total']}")
    if state.get("error"):
        sys.exit(f"The matrix stopped: {state['error']}")

    runs = {r["id"]: r for r in call(base, "/api/runs")}
    rows = [runs[i] for i in state["run_ids"] if i in runs]
    verdicts = [(r.get("outcome") or {}).get("verdict") or "ERROR" for r in rows]
    report = call(base, "/api/report.md?ids=" + ",".join(state["run_ids"]))
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(report)

    counts = {v: verdicts.count(v) for v in sorted(set(verdicts))}
    print(f"\n{len(rows)} runs: " + ", ".join(f"{n} {v}" for v, n in counts.items()))
    for retry in state.get("retried") or []:
        c = retry["combo"]
        print(f"  retried once after an error: {c['issuer']} -> {c['verifier']} {c['format']} {c['scenario']}: "
              f"{(retry['first_error'] or '')[:160]}")
    for r, v in zip(rows, verdicts):
        if v in ("FAIL", "ERROR"):
            why = r.get("error") or "; ".join(g.get("summary", "") for g in r.get("suspected_gaps") or [])
            print(f"  {v:<5} {r['issuer']} -> {r['verifier']} {r['format']} {r['scenario']}: {why[:140]}")
    print(f"\nReport written to {args.out}")
    broken = counts.get("ERROR", 0) + (counts.get("FAIL", 0) if args.strict else 0)
    sys.exit(1 if broken else 0)


if __name__ == "__main__":
    main()
