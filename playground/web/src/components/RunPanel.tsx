import { PHASES } from '../parties'
import type { Catalog, Check, Run } from '../types'

const VERDICT_STYLE: Record<string, { fg: string; bg: string; line: string }> = {
  PASS: { fg: 'var(--ok)', bg: 'var(--ok-soft)', line: 'The verifier did what the standard expects.' },
  FAIL: { fg: 'var(--fail)', bg: 'var(--fail-soft)', line: "The verifier's answer doesn't match what the standard expects." },
  UNSUPPORTED: { fg: 'var(--warn)', bg: 'var(--warn-soft)', line: "This combination can't complete. The gap is recorded in the report." },
  ERROR: { fg: 'var(--fail)', bg: 'var(--fail-soft)', line: 'The run stopped before a verdict.' },
}

function PhaseTracker({ run }: { run: Run }) {
  const order = PHASES.map((p) => p.id)
  const reached = run.phase === 'done' ? order.length : order.indexOf(run.phase)
  const failed = run.status === 'error' || run.status === 'cancelled'
  return (
    <ol className="grid grid-cols-4 gap-1.5">
      {PHASES.map((ph, i) => {
        const count = run.steps.filter((s) => s.phase === ph.id).length
        const active = i === reached && (run.status === 'running' || run.status === 'waiting')
        const done = i < reached || (run.phase === 'done' && count > 0)
        const broken = failed && i === Math.min(reached, order.length - 1) && !done
        const color = broken ? 'var(--fail)' : done ? 'var(--ok)' : active ? 'var(--accent)' : 'var(--line-strong)'
        return (
          <li key={ph.id} className="min-w-0">
            <div className="h-1 rounded-full" style={{ background: color }} />
            <div className="mt-1.5 flex items-center gap-1.5">
              {active && <span className="pulse size-1.5 shrink-0 rounded-full" style={{ background: 'var(--accent)' }} />}
              <span className="text-[0.8rem] font-semibold" style={{ color: done || active ? 'var(--ink)' : 'var(--faint)' }}>{ph.label}</span>
            </div>
            <div className="truncate font-mono text-[0.66rem] text-faint">{count ? `${count} step${count > 1 ? 's' : ''}` : ph.protocol}</div>
          </li>
        )
      })}
    </ol>
  )
}

function CheckList({ title, checks, empty }: { title: string; checks: Check[]; empty: string }) {
  return (
    <div className="min-w-0">
      <div className="eyebrow mb-1.5">{title}</div>
      {checks.length === 0 ? (
        <p className="text-[0.8rem] text-muted">{empty}</p>
      ) : (
        <ul className="flex flex-col divide-y divide-line">
          {checks.map((c, i) => (
            <li key={c.id ?? i} className="flex gap-2 py-1.5 text-[0.8rem]">
              <span className="w-4 shrink-0 font-bold" style={{ color: c.ok === null ? 'var(--faint)' : c.ok ? 'var(--ok)' : 'var(--fail)' }}>
                {c.ok === null ? '–' : c.ok ? '✓' : '✕'}
              </span>
              <span className="min-w-0">
                {c.label}
                {c.detail && <span className="block text-[0.74rem] break-words text-muted">{c.detail}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Awaiting({ run, onContinue, onCancel }: { run: Run; onContinue: () => void; onCancel: () => void }) {
  const a = run.awaiting!
  return (
    <div className="rounded-xl border p-4" style={{ borderColor: 'var(--wallet)', background: 'var(--wallet-soft)' }}>
      <div className="flex items-center gap-2">
        <span className="pulse size-2 rounded-full" style={{ background: 'var(--wallet)' }} />
        <h3 className="font-display text-base font-semibold">{a.title}</h3>
      </div>
      <ol className="mt-2 list-decimal space-y-1 pl-5 text-[0.84rem]">
        {a.instructions.map((line) => <li key={line}>{line}</li>)}
      </ol>
      <div className="mt-3 flex flex-wrap gap-2">
        <a
          href={a.link}
          target="_blank"
          rel="noreferrer"
          className="rounded-lg px-4 py-2 text-[0.85rem] font-semibold"
          style={{ background: 'var(--wallet)', color: 'var(--surface)' }}
        >
          {a.kind === 'inji_web_issue' ? 'Open Inji Web' : 'Open the request in Inji Web'}
        </a>
        {a.kind === 'inji_web_issue' && (
          <button type="button" onClick={onContinue} className="rounded-lg border border-line-strong bg-surface px-4 py-2 text-[0.85rem] font-semibold">
            The card is in my wallet
          </button>
        )}
        <button type="button" onClick={onCancel} className="px-2 py-2 text-[0.8rem] text-muted hover:text-ink">Cancel run</button>
      </div>
      {a.qr && (
        <div className="mt-4 flex flex-wrap items-start gap-3 border-t border-line pt-3">
          <img src={a.qr} alt="OpenID4VP request as a QR code" className="size-36 rounded-lg bg-white p-1.5" />
          <p className="max-w-[18rem] text-[0.78rem] text-muted">
            Or scan it with a phone wallet (cross-device flow). The answer goes to Inji Verify through the https tunnel,
            so the phone doesn't need to be on this network. The wallet has to trust this verifier.
          </p>
        </div>
      )}
    </div>
  )
}

function Claims({ claims }: { claims: Record<string, unknown> }) {
  const rows = Object.entries(claims).filter(([k]) => k !== 'id')
  if (!rows.length) return null
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[0.8rem]">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted">{k}</dt>
          <dd className="min-w-0 font-mono text-[0.76rem] break-all">{typeof v === 'object' ? JSON.stringify(v) : String(v)}</dd>
        </div>
      ))}
    </dl>
  )
}

export function RunPanel({ run, catalog, onContinue, onCancel }: {
  run: Run; catalog: Catalog; onContinue: () => void; onCancel: () => void
}) {
  const verdict = run.outcome?.verdict ?? (run.status === 'error' || run.status === 'cancelled' ? 'ERROR' : null)
  const vs = verdict ? VERDICT_STYLE[verdict] : null
  const fmt = catalog.formats[run.format]
  const claims = (run.credential?.claims ?? null) as Record<string, unknown> | null
  const secs = run.duration_ms ? (run.duration_ms / 1000).toFixed(1) : null

  return (
    <section className="flex min-w-0 flex-col gap-4 rounded-2xl border border-line bg-surface p-4 shadow-panel" aria-label="Run">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-base font-semibold">
          Run <span className="font-mono text-[0.8rem] font-normal text-faint">{run.id}</span>
        </h2>
        <span className="rounded-full px-2.5 py-0.5 text-[0.72rem] font-semibold" style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}>
          {fmt?.label} · {catalog.scenarios[run.scenario]?.label}
        </span>
      </div>

      <PhaseTracker run={run} />

      {run.status === 'waiting' && run.awaiting && <Awaiting run={run} onContinue={onContinue} onCancel={onCancel} />}

      {run.status === 'running' && (
        <div className="flex items-center justify-between gap-3 text-[0.82rem] text-muted">
          <span>Working on <strong className="text-ink">{PHASES.find((p) => p.id === run.phase)?.label ?? run.phase}</strong>…</span>
          <button type="button" onClick={onCancel} className="text-[0.8rem] hover:text-ink">Cancel</button>
        </div>
      )}

      {vs && verdict && (
        <div className="rounded-xl p-4" style={{ background: vs.bg }}>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <div className="eyebrow" style={{ color: vs.fg }}>Verdict</div>
              <div className="font-display text-4xl leading-none font-bold tracking-tight" style={{ color: vs.fg }}>{verdict}</div>
            </div>
            {run.outcome && (
              <dl className="grid grid-cols-2 gap-x-5 text-[0.78rem] tabular">
                <dt className="text-muted">Expected</dt><dt className="text-muted">Inji Verify said</dt>
                <dd className="font-semibold">{run.outcome.expected}</dd><dd className="font-semibold">{run.outcome.result}</dd>
              </dl>
            )}
          </div>
          <p className="mt-2 text-[0.82rem]">{vs.line}</p>
          {run.outcome?.explanation && <p className="mt-1 text-[0.8rem] text-muted">{run.outcome.explanation}</p>}
          {run.error && <p className="mt-2 text-[0.8rem] break-words" style={{ color: 'var(--fail)' }}>{run.error}</p>}
        </div>
      )}

      {run.suspected_gaps.length > 0 && (
        <div className="flex flex-col gap-2">
          {run.suspected_gaps.map((g) => (
            <div key={g.summary} className="rounded-xl border p-3 text-[0.82rem]" style={{ borderColor: 'var(--fail)', background: 'var(--fail-soft)' }}>
              <strong style={{ color: 'var(--fail)' }}>Interoperability gap{g.finding ? ` ${g.finding.join(', ')}` : ''}: </strong>
              {g.summary}
            </div>
          ))}
        </div>
      )}

      {(run.verifier_result?.checks?.length || run.playground_checks.length) ? (
        <div className="flex flex-col gap-4">
          <CheckList title="Inji Verify's checks" checks={run.verifier_result?.checks ?? []} empty="No result from Inji Verify." />
          <CheckList title="Playground's own checks" checks={run.playground_checks} empty="Not run." />
        </div>
      ) : null}

      {run.credential && (
        <details className="group rounded-xl border border-line p-3" open={!run.outcome}>
          <summary className="cursor-pointer list-none text-[0.84rem] font-semibold">
            Credential in the wallet
            <span className="ml-2 font-mono text-[0.72rem] font-normal text-muted">{run.proof_type}</span>
          </summary>
          <div className="mt-2 flex flex-col gap-2">
            {typeof run.credential.issuer === 'string' && (
              <p className="font-mono text-[0.74rem] break-all text-muted">issuer {run.credential.issuer}</p>
            )}
            {claims && <Claims claims={claims} />}
          </div>
        </details>
      )}

      {secs && <p className="text-[0.74rem] text-faint tabular">Finished in {secs} s</p>}
    </section>
  )
}
