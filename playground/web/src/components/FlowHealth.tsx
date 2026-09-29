import type { Catalog, RunSummary } from '../types'

// FR16: how often each flow completes and gives the right verdict, and how long it takes.
function quantile(sorted: number[], q: number) {
  if (!sorted.length) return null
  const i = Math.min(sorted.length - 1, Math.max(0, Math.ceil(q * sorted.length) - 1))
  return sorted[i]
}
const secs = (ms: number | null) => (ms === null ? '–' : `${(ms / 1000).toFixed(1)} s`)

function Rate({ value, total }: { value: number; total: number }) {
  const pct = total ? Math.round((value / total) * 100) : 0
  const color = pct >= 90 ? 'var(--ok)' : pct >= 60 ? 'var(--warn)' : 'var(--fail)'
  return (
    <div className="flex min-w-[7rem] items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-neutral-soft">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="w-9 text-right font-mono text-[0.74rem] tabular">{pct}%</span>
    </div>
  )
}

export function FlowHealth({ runs, catalog }: { runs: RunSummary[]; catalog: Catalog }) {
  const finished = runs.filter((r) => r.status === 'done' || r.status === 'error')
  const groups = new Map<string, RunSummary[]>()
  for (const r of finished) {
    const key = `${r.issuer}|${r.wallet}|${r.verifier}|${r.format}`
    groups.set(key, [...(groups.get(key) ?? []), r])
  }
  const rows = [...groups.entries()].map(([key, list]) => {
    const [issuer, wallet, verifier, format] = key.split('|')
    const timed = list.filter((r) => r.timings?.issue_ms !== undefined && r.status === 'done')
    const total = timed.map((r) => r.duration_ms ?? 0).sort((a, b) => a - b)
    const issue = timed.map((r) => r.timings!.issue_ms!).sort((a, b) => a - b)
    const present = timed.filter((r) => r.timings?.present_verify_ms !== undefined)
      .map((r) => r.timings!.present_verify_ms!).sort((a, b) => a - b)
    return {
      key, issuer, wallet, verifier, format, runs: list.length,
      completed: list.filter((r) => r.status === 'done' && r.outcome?.verdict !== 'ERROR').length,
      correct: list.filter((r) => r.outcome?.verdict === 'PASS').length,
      median: quantile(total, 0.5), p95: quantile(total, 0.95),
      issue: quantile(issue, 0.5), present: quantile(present, 0.5), timedRuns: timed.length,
    }
  }).sort((a, b) => b.runs - a.runs)

  const name = (kind: 'issuers' | 'wallets' | 'verifiers', id: string) => catalog[kind][id]?.name ?? id

  return (
    <section className="rounded-2xl border border-line bg-surface p-4 shadow-panel">
      <h3 className="font-display text-base font-semibold">Flow health</h3>
      <p className="mt-0.5 mb-3 max-w-[75ch] text-[0.8rem] text-muted">
        Completed means the run reached a verdict. Correct means the verifier gave the answer the standards expect,
        tamper scenarios included. Times are medians over automated runs; Inji Web runs wait on a person, so they
        count toward the rates but not the times.
      </p>
      {rows.length === 0 ? (
        <p className="text-[0.84rem] text-muted">No runs yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[52rem] text-[0.8rem]">
            <thead>
              <tr className="text-left">
                {['Issuer → Wallet → Verifier', 'Format', 'Runs', 'Completed', 'Correct verdict', 'Median', 'p95', 'Issue', 'Present + verify'].map((h) => (
                  <th key={h} className="eyebrow py-2 pr-3 font-semibold">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key} className="border-t border-line align-middle">
                  <td className="py-2 pr-3">
                    <span style={{ color: 'var(--issuer)' }}>{name('issuers', r.issuer)}</span>
                    <span className="text-faint"> → </span>
                    <span style={{ color: 'var(--wallet)' }}>{name('wallets', r.wallet)}</span>
                    <span className="text-faint"> → </span>
                    <span style={{ color: 'var(--verifier)' }}>{name('verifiers', r.verifier)}</span>
                  </td>
                  <td className="py-2 pr-3 whitespace-nowrap">{catalog.formats[r.format as keyof Catalog['formats']]?.short ?? r.format}</td>
                  <td className="py-2 pr-3 font-mono tabular">{r.runs}</td>
                  <td className="py-2 pr-3"><Rate value={r.completed} total={r.runs} /></td>
                  <td className="py-2 pr-3"><Rate value={r.correct} total={r.runs} /></td>
                  <td className="py-2 pr-3 font-mono tabular">{secs(r.median)}</td>
                  <td className="py-2 pr-3 font-mono tabular">{secs(r.p95)}</td>
                  <td className="py-2 pr-3 font-mono tabular">{secs(r.issue)}</td>
                  <td className="py-2 pr-3 font-mono tabular">{secs(r.present)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
