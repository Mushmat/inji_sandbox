import { useEffect, useState } from 'react'
import type { Health } from '../types'

type Theme = 'system' | 'light' | 'dark'

function readTheme(): Theme {
  try {
    const t = localStorage.getItem('playground-theme')
    return t === 'light' || t === 'dark' ? t : 'system'
  } catch {
    return 'system'
  }
}

function ThemeSwitch() {
  const [theme, setTheme] = useState<Theme>(readTheme)
  useEffect(() => {
    const root = document.documentElement
    if (theme === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', theme)
    try { localStorage.setItem('playground-theme', theme) } catch { /* private mode: just don't remember it */ }
  }, [theme])
  return (
    <label className="flex items-center gap-1.5 text-[0.76rem] text-muted" htmlFor="theme">
      Theme
      <select id="theme" value={theme} onChange={(e) => setTheme(e.target.value as Theme)}
        className="rounded-md border border-line bg-surface-2 px-1.5 py-0.5 text-[0.76rem] text-ink">
        <option value="system">System</option>
        <option value="light">Light</option>
        <option value="dark">Dark</option>
      </select>
    </label>
  )
}

export function Header({ health, tab, onTab }: { health: Health | null; tab: 'bench' | 'report'; onTab: (t: 'bench' | 'report') => void }) {
  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-[92rem] flex-wrap items-center justify-between gap-x-6 gap-y-3 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-6">
          <div>
            <h1 className="font-display text-xl leading-none font-bold tracking-tight">Inji Interop Playground</h1>
            <p className="mt-1 text-[0.76rem] text-muted">Issue, hold, present and verify across Inji Certify, Inji Web and Inji Verify</p>
          </div>
          <nav className="flex gap-1" aria-label="Sections">
            {(['bench', 'report'] as const).map((t) => (
              <button key={t} type="button" onClick={() => onTab(t)} aria-current={tab === t ? 'page' : undefined}
                className="rounded-lg px-3 py-1.5 text-[0.84rem] font-semibold"
                style={tab === t ? { background: 'var(--accent-soft)', color: 'var(--accent)' } : { color: 'var(--muted)' }}>
                {t === 'bench' ? 'Test bench' : 'Report'}
              </button>
            ))}
          </nav>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <ul className="flex flex-wrap items-center gap-x-3 gap-y-1" aria-label="Service status">
            {(health?.services ?? []).map((s) => (
              <li key={s.id} className="flex items-center gap-1.5 text-[0.76rem]" title={`${s.url} (${s.detail})`}>
                <span className="size-2 rounded-full" style={{ background: s.up ? 'var(--ok)' : 'var(--fail)' }} />
                <span className={s.up ? 'text-muted' : ''} style={s.up ? undefined : { color: 'var(--fail)' }}>{s.label}</span>
              </li>
            ))}
            {health && (
              <li className="flex items-center gap-1.5 text-[0.76rem]" title={health.did.detail}>
                <span className="size-2 rounded-full" style={{ background: health.did.ok ? 'var(--ok)' : 'var(--warn)' }} />
                <span className="text-muted">DID keys {health.did.ok ? 'match' : 'mismatch'}</span>
              </li>
            )}
            {!health && <li className="text-[0.76rem] text-faint">Checking services…</li>}
          </ul>
          <ThemeSwitch />
        </div>
      </div>
    </header>
  )
}
