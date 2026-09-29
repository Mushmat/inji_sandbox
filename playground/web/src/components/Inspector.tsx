import { useEffect, useMemo, useState } from 'react'
import { party, PHASES } from '../parties'
import type { Party, Step } from '../types'
import { JsonView } from './JsonView'
import { SequenceDiagram } from './SequenceDiagram'

function PartyChip({ p }: { p: Party | null }) {
  const meta = party(p)
  return (
    <span className="rounded px-1.5 py-px text-[0.66rem] font-semibold whitespace-nowrap" style={{ background: meta.soft, color: meta.color }}>
      {meta.short}
    </span>
  )
}

function StatusBadge({ step }: { step: Step }) {
  if (step.method === 'LOCAL') {
    return <span className="font-mono text-[0.68rem] text-faint">local</span>
  }
  const color = step.ok ? 'var(--ok)' : 'var(--fail)'
  return (
    <span className="font-mono text-[0.7rem] font-medium tabular" style={{ color }}>
      {step.method} {step.status ?? 'ERR'}
    </span>
  )
}

function StepRow({ step, selected, onSelect }: { step: Step; selected: boolean; onSelect: () => void }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className="step-in grid w-full grid-cols-[1.6rem_1fr] gap-2 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-surface-2"
      style={selected ? { background: 'var(--accent-soft)' } : undefined}
    >
      <span className="pt-px font-mono text-[0.7rem] text-faint tabular">{step.seq}</span>
      <span className="min-w-0">
        <span className="flex flex-wrap items-center gap-1">
          <PartyChip p={step.from} />
          {step.to && step.to !== step.from && (
            <>
              <span className="text-[0.7rem] text-faint">→</span>
              <PartyChip p={step.to} />
            </>
          )}
          <span className="ml-auto"><StatusBadge step={step} /></span>
        </span>
        <span className="mt-0.5 block text-[0.82rem] leading-snug" style={step.ok === false ? { color: 'var(--fail)' } : undefined}>
          {step.name}
        </span>
      </span>
    </button>
  )
}

function StepDetail({ step }: { step: Step }) {
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <PartyChip p={step.from} />
          {step.to && step.to !== step.from && <><span className="text-faint">→</span><PartyChip p={step.to} /></>}
          <StatusBadge step={step} />
        </div>
        <h3 className="mt-1.5 font-display text-lg leading-tight font-semibold">{step.seq}. {step.name}</h3>
        {step.url && <p className="mt-1 font-mono text-[0.72rem] break-all text-muted">{step.url}</p>}
        {step.note && <p className="mt-2 text-[0.82rem] leading-snug text-muted">{step.note}</p>}
      </div>
      {step.request !== undefined && step.request !== null && <JsonView label="Sent" value={step.request} />}
      {step.proof_jwt_decoded !== undefined && <JsonView label="Holder proof JWT, decoded" value={step.proof_jwt_decoded} />}
      <JsonView label={step.method === 'LOCAL' ? 'Detail' : 'Received'} value={step.response} />
    </div>
  )
}

export function Inspector({ steps, names, live }: { steps: Step[]; names: Partial<Record<Party, string>>; live: boolean }) {
  const [tab, setTab] = useState<'steps' | 'sequence'>('steps')
  const [selected, setSelected] = useState<number | null>(null)

  // follow the newest step while a run is live, unless the reader picked one
  const [pinned, setPinned] = useState(false)
  useEffect(() => {
    if (!pinned && steps.length) setSelected(steps[steps.length - 1].seq)
  }, [steps, pinned])
  useEffect(() => {
    if (steps.length === 0) setPinned(false)
  }, [steps.length])

  const current = useMemo(() => steps.find((s) => s.seq === selected) ?? null, [steps, selected])

  return (
    <section className="min-w-0 rounded-2xl border border-line bg-surface shadow-panel" aria-label="Protocol inspector">
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
        <div className="flex items-center gap-2">
          <h2 className="font-display text-base font-semibold">Protocol inspector</h2>
          {live && <span className="pulse size-2 rounded-full" style={{ background: 'var(--accent)' }} aria-label="live" />}
        </div>
        <div className="flex rounded-lg border border-line bg-surface-2 p-0.5 text-[0.78rem]" role="tablist">
          {(['steps', 'sequence'] as const).map((t) => (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={tab === t}
              onClick={() => setTab(t)}
              className="rounded-md px-3 py-1 font-medium"
              style={tab === t ? { background: 'var(--surface)', color: 'var(--ink)', boxShadow: 'var(--shadow)' } : { color: 'var(--muted)' }}
            >
              {t === 'steps' ? 'Messages' : 'Sequence diagram'}
            </button>
          ))}
        </div>
      </div>

      {steps.length === 0 ? (
        <p className="px-4 py-10 text-center text-[0.85rem] text-muted">
          Every request and response between issuer, wallet and verifier shows up here as the run happens.
        </p>
      ) : tab === 'sequence' ? (
        <div className="p-4"><SequenceDiagram steps={steps} names={names} /></div>
      ) : (
        <div className="grid min-w-0 md:grid-cols-[minmax(15rem,20rem)_1fr]">
          <nav className="max-h-[42rem] overflow-y-auto border-b border-line p-2 md:border-r md:border-b-0">
            {PHASES.map((ph) => {
              const inPhase = steps.filter((s) => s.phase === ph.id)
              if (!inPhase.length) return null
              return (
                <div key={ph.id} className="mb-2">
                  <div className="eyebrow px-2 pt-1.5 pb-1">{ph.label} · {ph.protocol}</div>
                  {inPhase.map((s) => (
                    <StepRow
                      key={s.seq}
                      step={s}
                      selected={s.seq === selected}
                      onSelect={() => { setSelected(s.seq); setPinned(true) }}
                    />
                  ))}
                </div>
              )
            })}
          </nav>
          <div className="min-w-0 p-4">{current ? <StepDetail step={current} /> : null}</div>
        </div>
      )}
    </section>
  )
}
