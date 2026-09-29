import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Catalog, MatrixState } from '../types'

// FR14: every automated combination, one after another. The same thing runs nightly in CI
// (playground/run_matrix.py, .github/workflows/nightly-matrix.yml).
export function MatrixCard({ catalog, onProgress }: { catalog: Catalog; onProgress: () => void }) {
  const [state, setState] = useState<MatrixState | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { api.matrix().then(setState).catch(() => {}) }, [])
  useEffect(() => {
    if (!state?.running) return
    const t = setInterval(() => {
      api.matrix().then((s) => {
        if (s.done !== state.done || !s.running) onProgress()
        setState(s)
      }).catch(() => {})
    }, 2000)
    return () => clearInterval(t)
  }, [state?.running, state?.done, onProgress])

  async function start(preset: 'quick' | 'full') {
    setError(null)
    try { setState(await api.startMatrix(preset)) } catch (e) { setError((e as Error).message) }
  }

  const pct = state?.total ? Math.round((state.done / state.total) * 100) : 0
  const c = state?.current
  const label = c && `${catalog.issuers[c.issuer]?.name} → ${catalog.verifiers[c.verifier]?.name}, ${catalog.formats[c.format]?.short}, ${catalog.scenarios[c.scenario]?.label}`

  return (
    <section className="rounded-2xl border border-line bg-surface p-4 shadow-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-[70ch]">
          <h3 className="font-display text-base font-semibold">Test matrix</h3>
          <p className="mt-0.5 text-[0.8rem] text-muted">
            Runs every automated issuer, verifier and format combination, one after another. Quick is honest runs
            only; full adds every tamper scenario. Inji Web runs need a person, so run those from the bench.
          </p>
        </div>
        {state?.running ? (
          <button type="button" onClick={() => api.cancelMatrix().then(setState)} className="rounded-lg border border-line-strong px-3.5 py-2 text-[0.84rem] font-semibold">
            Stop after this run
          </button>
        ) : (
          <div className="flex gap-2">
            <button type="button" onClick={() => start('quick')} className="rounded-lg px-3.5 py-2 text-[0.84rem] font-semibold"
              style={{ background: 'var(--accent)', color: 'var(--accent-ink)' }}>
              Quick matrix ({state?.sizes.quick ?? '…'} runs)
            </button>
            <button type="button" onClick={() => start('full')} className="rounded-lg border border-line-strong px-3.5 py-2 text-[0.84rem] font-semibold">
              Full matrix ({state?.sizes.full ?? '…'} runs)
            </button>
          </div>
        )}
      </div>
      {state && (state.running || state.finished_at) && (
        <div className="mt-3">
          <div className="h-1.5 overflow-hidden rounded-full bg-neutral-soft">
            <div className="h-full rounded-full transition-[width]" style={{ width: `${pct}%`, background: 'var(--accent)' }} />
          </div>
          <p className="mt-1.5 text-[0.78rem] text-muted tabular">
            {state.running
              ? <>Run {state.done + 1} of {state.total}{label ? `: ${label}` : ''}</>
              : <>Last {state.preset} matrix: {state.done} of {state.total} runs{state.cancelled ? ', stopped early' : ''}, finished {new Date(state.finished_at!).toLocaleString()}. Results are in the tables below.</>}
          </p>
        </div>
      )}
      {(error || state?.error) && <p className="mt-2 text-[0.8rem]" style={{ color: 'var(--fail)' }}>{error || state?.error}</p>}
    </section>
  )
}
