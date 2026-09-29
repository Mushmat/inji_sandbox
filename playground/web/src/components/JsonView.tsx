import { useState, type ReactNode } from 'react'

const JWT = /^[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*$/

function b64urlJson(part: string): unknown {
  const padded = part.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (part.length % 4)) % 4)
  return JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(padded), (c) => c.charCodeAt(0))))
}

export function decodeJwt(value: string): { header: unknown; payload: unknown } | null {
  if (!JWT.test(value)) return null
  try {
    const [h, p] = value.split('.')
    return { header: b64urlJson(h), payload: b64urlJson(p) }
  } catch {
    return null
  }
}

function Scalar({ value }: { value: unknown }) {
  if (typeof value === 'string') {
    return <span style={{ color: 'var(--code-string)' }}>"{value}"</span>
  }
  if (typeof value === 'number') return <span style={{ color: 'var(--code-number)' }}>{value}</span>
  return <span style={{ color: 'var(--code-literal)' }}>{String(value)}</span>
}

function JwtString({ value, depth }: { value: string; depth: number }) {
  const [open, setOpen] = useState(false)
  const decoded = decodeJwt(value)
  return (
    <>
      <Scalar value={value} />
      {decoded && (
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="ml-2 rounded border border-line px-1.5 text-[0.68rem] font-sans text-accent hover:bg-accent-soft"
        >
          {open ? 'hide decoded JWT' : 'decode JWT'}
        </button>
      )}
      {decoded && open && (
        <div className="my-1 rounded-md border border-dashed border-line-strong bg-surface p-2">
          <Node value={decoded} depth={depth + 1} />
        </div>
      )}
    </>
  )
}

function Node({ value, depth }: { value: unknown; depth: number }): ReactNode {
  const pad = '  '.repeat(depth)
  if (Array.isArray(value)) {
    if (value.length === 0) return '[]'
    return (
      <>
        {'[\n'}
        {value.map((v, i) => (
          <span key={i}>
            {pad}{'  '}<Node value={v} depth={depth + 1} />{i < value.length - 1 ? ',' : ''}{'\n'}
          </span>
        ))}
        {pad}{']'}
      </>
    )
  }
  if (value && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
    if (entries.length === 0) return '{}'
    return (
      <>
        {'{\n'}
        {entries.map(([k, v], i) => (
          <span key={k}>
            {pad}{'  '}<span style={{ color: 'var(--code-key)' }}>"{k}"</span>{': '}
            <Node value={v} depth={depth + 1} />{i < entries.length - 1 ? ',' : ''}{'\n'}
          </span>
        ))}
        {pad}{'}'}
      </>
    )
  }
  if (typeof value === 'string') return <JwtString value={value} depth={depth} />
  return <Scalar value={value} />
}

export function JsonView({ value, label }: { value: unknown; label: string }) {
  const [copied, setCopied] = useState(false)
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2)

  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1400)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="min-w-0">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="eyebrow">{label}</span>
        <button type="button" onClick={copy} className="text-xs text-muted hover:text-accent">
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="max-h-[28rem] overflow-auto rounded-lg border border-line bg-surface-2 p-3 font-mono text-[0.74rem] leading-relaxed break-all whitespace-pre-wrap">
        {value === undefined || value === null ? <span className="text-faint">nothing</span> : <Node value={value} depth={0} />}
      </pre>
    </div>
  )
}
