import { useMemo, useState } from 'react'
import type { Catalog, FormatId, RunSummary } from '../types'
import { FlowHealth } from './FlowHealth'
import { MatrixCard } from './MatrixCard'

const VERDICT_COLORS: Record<string, { fg: string; bg: string }> = {
  PASS: { fg: 'var(--ok)', bg: 'var(--ok-soft)' },
  FAIL: { fg: 'var(--fail)', bg: 'var(--fail-soft)' },
  UNSUPPORTED: { fg: 'var(--warn)', bg: 'var(--warn-soft)' },
  ERROR: { fg: 'var(--fail)', bg: 'var(--fail-soft)' },
}

function verdictOf(r: RunSummary) {
  return r.outcome?.verdict ?? (r.status === 'done' ? 'ERROR' : r.status.toUpperCase())
}

function Verdict({ v }: { v: string }) {
  const c = VERDICT_COLORS[v] ?? { fg: 'var(--muted)', bg: 'var(--neutral-soft)' }
  return <span className="rounded-md px-2 py-0.5 text-[0.7rem] font-bold tracking-wide" style={{ color: c.fg, background: c.bg }}>{v}</span>
}

function Filter({ id, label, value, options, onChange }: {
  id: string; label: string; value: string; options: [string, string][]; onChange: (v: string) => void
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1" htmlFor={id}>
      <span className="eyebrow">{label}</span>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-line bg-surface-2 px-2.5 py-1.5 text-[0.82rem] text-ink">
        <option value="">All</option>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  )
}

export function ReportView({ runs, catalog, onOpen, onClear, onRefresh }: {
  runs: RunSummary[]; catalog: Catalog; onOpen: (id: string) => void; onClear: () => void; onRefresh: () => void
}) {
  const [f, setF] = useState({ format: '', verdict: '', wallet: '', verifier: '', version: '' })
  const [confirming, setConfirming] = useState(false)
  const finished = runs.filter((r) => r.status === 'done' || r.status === 'error')

  const name = (kind: 'issuers' | 'wallets' | 'verifiers', id: string) => catalog[kind][id]?.name ?? id
  const versionLabel = (r: RunSummary) => Object.entries(r.versions ?? {}).map(([k, v]) => `${k} ${v}`).join(', ')
  const versions = [...new Set(finished.map(versionLabel))].filter(Boolean)

  const filtered = finished.filter((r) =>
    (!f.format || r.format === f.format) && (!f.verdict || verdictOf(r) === f.verdict) &&
    (!f.wallet || r.wallet === f.wallet) && (!f.verifier || r.verifier === f.verifier) &&
    (!f.version || versionLabel(r) === f.version))

  const matrix = useMemo(() => {
    const latest = new Map<string, RunSummary>()
    for (const r of finished) {
      if (r.scenario !== 'none') continue
      const key = `${r.issuer}|${r.wallet}|${r.verifier}|${r.format}`
      if (!latest.has(key)) latest.set(key, r)
    }
    const paths = [...new Set([...latest.keys()].map((k) => k.split('|').slice(0, 3).join('|')))]
    return { latest, paths }
  }, [finished])

  const formats = Object.keys(catalog.formats) as FormatId[]
  const counts = finished.reduce<Record<string, number>>((acc, r) => { const v = verdictOf(r); acc[v] = (acc[v] ?? 0) + 1; return acc }, {})

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-display text-2xl font-semibold tracking-tight">Interoperability report</h2>
          <p className="mt-1 text-[0.85rem] text-muted tabular">
            {finished.length} runs · {counts.PASS ?? 0} pass · {counts.FAIL ?? 0} fail · {counts.UNSUPPORTED ?? 0} unsupported · {counts.ERROR ?? 0} error
          </p>
        </div>
        <div className="flex items-center gap-2">
          <a href="/api/report.md" download className="rounded-lg border border-line-strong bg-surface px-3.5 py-2 text-[0.84rem] font-semibold">
            Export markdown
          </a>
          {confirming ? (
            <span className="flex items-center gap-2 text-[0.82rem]">
              Delete all runs?
              <button type="button" onClick={() => { onClear(); setConfirming(false) }} className="font-semibold" style={{ color: 'var(--fail)' }}>Delete</button>
              <button type="button" onClick={() => setConfirming(false)} className="text-muted">Keep</button>
            </span>
          ) : (
            <button type="button" onClick={() => setConfirming(true)} className="px-2 py-2 text-[0.82rem] text-muted hover:text-ink">Clear history</button>
          )}
        </div>
      </div>

      <MatrixCard catalog={catalog} onProgress={onRefresh} />

      <section className="rounded-2xl border border-line bg-surface p-4 shadow-panel">
        <h3 className="font-display text-base font-semibold">Compatibility matrix</h3>
        <p className="mt-0.5 mb-3 text-[0.8rem] text-muted">Latest honest run for each path and format. Tamper scenarios are in the history below.</p>
        {matrix.paths.length === 0 ? (
          <p className="text-[0.84rem] text-muted">No honest runs yet. Run one from the bench and it lands here.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[34rem] text-[0.82rem]">
              <thead>
                <tr className="text-left">
                  <th className="eyebrow py-2 pr-3 font-semibold">Issuer → Wallet → Verifier</th>
                  {formats.map((fm) => <th key={fm} className="eyebrow px-3 py-2 font-semibold">{catalog.formats[fm].short}</th>)}
                </tr>
              </thead>
              <tbody>
                {matrix.paths.map((p) => {
                  const [i, w, v] = p.split('|')
                  return (
                    <tr key={p} className="border-t border-line">
                      <td className="py-2 pr-3">
                        <span style={{ color: 'var(--issuer)' }}>{name('issuers', i)}</span>
                        <span className="text-faint"> → </span>
                        <span style={{ color: 'var(--wallet)' }}>{name('wallets', w)}</span>
                        <span className="text-faint"> → </span>
                        <span style={{ color: 'var(--verifier)' }}>{name('verifiers', v)}</span>
                      </td>
                      {formats.map((fm) => {
                        const r = matrix.latest.get(`${p}|${fm}`)
                        return (
                          <td key={fm} className="px-3 py-2">
                            {r ? (
                              <button type="button" onClick={() => onOpen(r.id)} title={r.proof_type ?? undefined}>
                                <Verdict v={verdictOf(r)} />
                              </button>
                            ) : <span className="text-faint">not run</span>}
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <FlowHealth runs={runs} catalog={catalog} />

      <section className="rounded-2xl border border-line bg-surface p-4 shadow-panel">
        <h3 className="font-display text-base font-semibold">Run history</h3>
        <div className="mt-3 mb-3 grid grid-cols-2 gap-3 md:grid-cols-5">
          <Filter id="f-format" label="Format" value={f.format} onChange={(v) => setF({ ...f, format: v })}
            options={formats.map((fm) => [fm, catalog.formats[fm].short])} />
          <Filter id="f-verdict" label="Verdict" value={f.verdict} onChange={(v) => setF({ ...f, verdict: v })}
            options={['PASS', 'FAIL', 'UNSUPPORTED', 'ERROR'].map((v) => [v, v])} />
          <Filter id="f-wallet" label="Wallet" value={f.wallet} onChange={(v) => setF({ ...f, wallet: v })}
            options={Object.entries(catalog.wallets).map(([id, o]) => [id, o.name])} />
          <Filter id="f-verifier" label="Verifier" value={f.verifier} onChange={(v) => setF({ ...f, verifier: v })}
            options={Object.entries(catalog.verifiers).map(([id, o]) => [id, o.name])} />
          <Filter id="f-version" label="Module versions" value={f.version} onChange={(v) => setF({ ...f, version: v })}
            options={versions.map((v) => [v, v])} />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[56rem] text-[0.8rem]">
            <thead>
              <tr className="text-left">
                {['When', 'Issuer', 'Wallet', 'Verifier', 'Format', 'Proof type', 'Scenario', 'Expected', 'Result', 'Verdict', 'Detail'].map((h) => (
                  <th key={h} className="eyebrow py-2 pr-3 font-semibold">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => {
                const detail = r.error || r.unsupported || r.suspected_gaps?.map((g) => (g.finding ? `${g.finding.join(', ')}: ` : '') + g.summary).join(' ')
                return (
                  <tr key={r.id} onClick={() => onOpen(r.id)} className="cursor-pointer border-t border-line align-top hover:bg-surface-2">
                    <td className="py-2 pr-3 font-mono text-[0.72rem] whitespace-nowrap text-muted tabular">
                      {new Date(r.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td className="py-2 pr-3">{name('issuers', r.issuer)}</td>
                    <td className="py-2 pr-3">{name('wallets', r.wallet)}</td>
                    <td className="py-2 pr-3">{name('verifiers', r.verifier)}</td>
                    <td className="py-2 pr-3 whitespace-nowrap">{catalog.formats[r.format]?.short}</td>
                    <td className="py-2 pr-3 font-mono text-[0.72rem]">{r.proof_type ?? '–'}</td>
                    <td className="py-2 pr-3">{catalog.scenarios[r.scenario]?.label}</td>
                    <td className="py-2 pr-3 tabular">{r.outcome?.expected ?? '–'}</td>
                    <td className="py-2 pr-3 tabular">{r.outcome?.result ?? '–'}</td>
                    <td className="py-2 pr-3"><Verdict v={verdictOf(r)} /></td>
                    <td className="max-w-[22rem] py-2 pr-3 text-[0.76rem] text-muted">{detail || '–'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {filtered.length === 0 && <p className="py-6 text-center text-[0.84rem] text-muted">No runs match these filters.</p>}
        </div>
      </section>
    </div>
  )
}
