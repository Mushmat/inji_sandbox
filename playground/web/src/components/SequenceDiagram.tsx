import { useEffect, useId, useRef, useState } from 'react'
import { PARTIES } from '../parties'
import type { Party, Step } from '../types'

const ALIAS: Record<Party, string> = {
  issuer: 'I', auth_server: 'A', wallet: 'W', relying_party: 'R', verifier: 'V', playground: 'P',
}
const ORDER: Party[] = ['issuer', 'auth_server', 'wallet', 'relying_party', 'verifier', 'playground']

// Mermaid's message grammar treats these as syntax, so they can't appear in labels.
const clean = (s: string) => s.replace(/[;:#{}<>]/g, ' ').replace(/\s+/g, ' ').trim()

export function toMermaid(steps: Step[], names: Partial<Record<Party, string>>): string {
  const used = new Set<Party>()
  steps.forEach((s) => { if (s.from) used.add(s.from); if (s.to) used.add(s.to) })
  const lines = ['sequenceDiagram']
  ORDER.filter((p) => used.has(p)).forEach((p) => {
    lines.push(`  participant ${ALIAS[p]} as ${clean(names[p] ?? PARTIES[p].label)}`)
  })
  for (const s of steps) {
    const from = s.from ? ALIAS[s.from] : 'P'
    const to = s.to ? ALIAS[s.to] : from
    const label = clean(`${s.seq}. ${s.name}`)
    if (s.method === 'LOCAL' || from === to) {
      lines.push(`  Note over ${to}: ${label}`)
    } else {
      lines.push(`  ${from}->>${to}: ${label}`)
      lines.push(`  ${to}${s.ok ? '-->>' : '--x'}${from}: ${s.status ?? 'no answer'}`)
    }
  }
  return lines.join('\n')
}

function cssVar(name: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

export function SequenceDiagram({ steps, names }: { steps: Step[]; names: Partial<Record<Party, string>> }) {
  const ref = useRef<HTMLDivElement>(null)
  const id = useId().replace(/:/g, '')
  const [error, setError] = useState<string | null>(null)
  const source = toMermaid(steps, names)

  useEffect(() => {
    let cancelled = false
    // Mermaid is large, so it loads the first time someone opens this tab.
    import('mermaid')
      .then(({ default: mermaid }) => {
        mermaid.initialize({
          startOnLoad: false,
          theme: 'base',
          securityLevel: 'strict',
          fontFamily: cssVar('--font-body'),
          themeVariables: {
            background: cssVar('--surface'),
            primaryColor: cssVar('--surface-2'),
            primaryBorderColor: cssVar('--line-strong'),
            primaryTextColor: cssVar('--ink'),
            actorBkg: cssVar('--surface-2'),
            actorBorder: cssVar('--line-strong'),
            actorTextColor: cssVar('--ink'),
            actorLineColor: cssVar('--line-strong'),
            signalColor: cssVar('--muted'),
            signalTextColor: cssVar('--ink'),
            noteBkgColor: cssVar('--accent-soft'),
            noteBorderColor: cssVar('--line'),
            noteTextColor: cssVar('--ink'),
            labelBoxBkgColor: cssVar('--surface-2'),
            labelTextColor: cssVar('--ink'),
          },
          sequence: { mirrorActors: false, showSequenceNumbers: false, messageFontSize: 12, noteFontSize: 12, actorFontSize: 13 },
        })
        return mermaid.render(`seq-${id}-${steps.length}`, source)
      })
      .then(({ svg }) => {
        if (!cancelled && ref.current) {
          ref.current.innerHTML = svg
          setError(null)
        }
      })
      .catch((e: unknown) => { if (!cancelled) setError(String(e)) })
    return () => { cancelled = true }
  }, [source, id, steps.length])

  return (
    <div className="min-w-0">
      <p className="mb-3 text-[0.8rem] text-muted">
        Drawn from the messages above, in order. Solid arrows are requests, dashed arrows the answers, notes are
        work a party does on its own.
      </p>
      {error && <p className="mb-2 text-[0.8rem]" style={{ color: 'var(--fail)' }}>Couldn't draw the diagram: {error}</p>}
      <div ref={ref} className="sequence overflow-x-auto" />
    </div>
  )
}
