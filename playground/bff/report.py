"""The interoperability report as markdown: a matrix of the latest result per combination, then every run."""

from datetime import datetime, timezone

import catalog


def _name(table, key):
    return table.get(key, {}).get("name", key)


def markdown(runs: list) -> str:
    fmt = catalog.FORMATS
    finished = [r for r in runs if r.get("status") in ("done", "error")]
    lines = [
        "# Inji Interoperability Report",
        "",
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from {len(finished)} runs.",
        "",
    ]
    versions = next((r["versions"] for r in finished if r.get("versions")), {})
    if versions:
        lines += ["Module versions: " + ", ".join(f"{k} {v}" for k, v in sorted(versions.items())), ""]

    lines += ["## Matrix (latest honest run per combination)", "",
              "| Issuer | Wallet | Verifier | Format | Proof type | Result | Verdict |",
              "|---|---|---|---|---|---|---|"]
    seen = set()
    for r in finished:  # newest first, so the first one wins
        if r.get("scenario") != "none":
            continue
        key = (r["issuer"], r["wallet"], r["verifier"], r["format"])
        if key in seen:
            continue
        seen.add(key)
        o = r.get("outcome") or {}
        lines.append(f"| {_name(catalog.ISSUERS, r['issuer'])} | {_name(catalog.WALLETS, r['wallet'])} | "
                     f"{_name(catalog.VERIFIERS, r['verifier'])} | {fmt.get(r['format'], {}).get('short', r['format'])} | "
                     f"{r.get('proof_type') or '-'} | {o.get('result', '-')} | {o.get('verdict', 'ERROR')} |")

    lines += ["", "## Flow health", "",
              "Automated runs only for the times; Inji Web runs wait on a person.", "",
              "| Issuer | Wallet | Verifier | Format | Runs | Completed | Correct verdict | Median | p95 |",
              "|---|---|---|---|---|---|---|---|---|"]
    groups = {}
    for r in finished:
        groups.setdefault((r["issuer"], r["wallet"], r["verifier"], r["format"]), []).append(r)
    for (i, w, v, f), runs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        done = [r for r in runs if r.get("status") == "done" and (r.get("outcome") or {}).get("verdict") != "ERROR"]
        correct = [r for r in runs if (r.get("outcome") or {}).get("verdict") == "PASS"]
        times = sorted(r["duration_ms"] for r in runs if (r.get("timings") or {}).get("issue_ms") is not None
                       and r.get("duration_ms"))
        med = f"{times[len(times) // 2] / 1000:.1f} s" if times else "-"
        p95 = f"{times[min(len(times) - 1, max(0, -(-95 * len(times) // 100) - 1))] / 1000:.1f} s" if times else "-"
        lines.append(f"| {_name(catalog.ISSUERS, i)} | {_name(catalog.WALLETS, w)} | {_name(catalog.VERIFIERS, v)} | "
                     f"{fmt.get(f, {}).get('short', f)} | {len(runs)} | {round(100 * len(done) / len(runs))}% | "
                     f"{round(100 * len(correct) / len(runs))}% | {med} | {p95} |")

    lines += ["", "## Every run", "",
              "| When (UTC) | Issuer | Wallet | Verifier | Format | Scenario | Expected | Result | Verdict | Detail |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for r in finished:
        o = r.get("outcome") or {}
        detail = r.get("error") or r.get("unsupported") or "; ".join(
            g.get("summary", "") for g in r.get("suspected_gaps") or []) or ""
        detail = detail.replace("|", "/").replace("\n", " ")[:220]
        lines.append(f"| {(r.get('created_at') or '')[:19].replace('T', ' ')} | {_name(catalog.ISSUERS, r['issuer'])} | "
                     f"{_name(catalog.WALLETS, r['wallet'])} | {_name(catalog.VERIFIERS, r['verifier'])} | "
                     f"{fmt.get(r['format'], {}).get('short', r['format'])} | "
                     f"{catalog.SCENARIOS.get(r['scenario'], {}).get('label', r['scenario'])} | "
                     f"{o.get('expected', '-')} | {o.get('result', '-')} | {o.get('verdict', 'ERROR')} | {detail} |")
    lines += ["", "Finding IDs (F*, W*, M*) refer to verify/docs/FINDINGS.md and wallet/README.md.", ""]
    return "\n".join(lines)
