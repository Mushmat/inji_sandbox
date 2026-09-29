import type { Catalog, Compatibility, FormatId, ScenarioId, Selection } from '../types'

export function RunControls({ catalog, selection, onChange, compat, onRun, busy, locked, waitingForCertify }: {
  catalog: Catalog
  selection: Selection
  onChange: (s: Selection) => void
  compat: Compatibility | null
  onRun: () => void
  busy: boolean
  locked: boolean
  waitingForCertify: boolean
}) {
  const scenarios = Object.entries(catalog.scenarios) as [ScenarioId, Catalog['scenarios'][ScenarioId]][]
  const interactive = catalog.wallets[selection.wallet]?.interactive

  return (
    <div className="grid gap-4 rounded-2xl border border-line bg-surface p-4 shadow-panel md:grid-cols-[auto_1fr_auto] md:items-end">
      <div className="min-w-0">
        <label className="eyebrow mb-1.5 block" id="format-label">Credential format</label>
        <div className="inline-flex flex-wrap rounded-lg border border-line bg-surface-2 p-0.5" role="radiogroup" aria-labelledby="format-label">
          {(Object.keys(catalog.formats) as FormatId[]).map((f) => {
            const on = selection.format === f
            return (
              <button
                key={f}
                id={`format-${f}`}
                type="button"
                role="radio"
                aria-checked={on}
                disabled={locked}
                title={catalog.formats[f].spec}
                onClick={() => onChange({ ...selection, format: f })}
                className="rounded-md px-3 py-1.5 text-[0.82rem] font-medium transition-colors disabled:opacity-60"
                style={on ? { background: 'var(--accent)', color: 'var(--accent-ink)' } : { color: 'var(--muted)' }}
              >
                {catalog.formats[f].label}
              </button>
            )
          })}
        </div>
      </div>

      <div className="min-w-0">
        <label className="eyebrow mb-1.5 block" htmlFor="scenario">Scenario</label>
        <select
          id="scenario"
          value={selection.scenario}
          disabled={locked}
          onChange={(e) => onChange({ ...selection, scenario: e.target.value as ScenarioId })}
          className="w-full rounded-lg border border-line bg-surface-2 px-3 py-2 text-[0.85rem] text-ink disabled:opacity-60"
        >
          <optgroup label="Normal">
            {scenarios.filter(([, s]) => !s.tamper).map(([id, s]) => (
              <option key={id} value={id}>{s.label}, expect {s.expected}</option>
            ))}
          </optgroup>
          <optgroup label="Tamper mode">
            {scenarios.filter(([, s]) => s.tamper).map(([id, s]) => (
              <option key={id} value={id}>{s.label}, expect {s.expected}</option>
            ))}
          </optgroup>
        </select>
      </div>

      <button
        type="button"
        onClick={onRun}
        disabled={busy || locked || waitingForCertify || !compat?.runnable}
        className="rounded-lg px-5 py-2.5 font-semibold transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45"
        style={{ background: 'var(--accent)', color: 'var(--accent-ink)' }}
      >
        {busy ? 'Starting…' : locked ? 'Run in progress' : waitingForCertify ? 'Certify is restarting' : interactive ? 'Start guided run' : 'Run'}
      </button>

      {compat && (compat.blockers.length > 0 || compat.limits.length > 0) && (
        <ul className="flex flex-col gap-1.5 md:col-span-3">
          {compat.blockers.map((b) => (
            <li key={b} className="rounded-lg px-3 py-2 text-[0.8rem]" style={{ background: 'var(--fail-soft)', color: 'var(--fail)' }}>
              <strong className="font-semibold">Can't run: </strong>{b}
            </li>
          ))}
          {compat.limits.map((l) => (
            <li key={l} className="rounded-lg px-3 py-2 text-[0.8rem]" style={{ background: 'var(--warn-soft)', color: 'var(--warn)' }}>
              <strong className="font-semibold">Known limit: </strong>{l}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
