import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { Header } from './components/Header'
import { Inspector } from './components/Inspector'
import { ReportView } from './components/ReportView'
import { RoleSelector } from './components/RoleSelector'
import { RunControls } from './components/RunControls'
import { RunPanel } from './components/RunPanel'
import { SubjectCard } from './components/SubjectCard'
import type { Catalog, Compatibility, Health, IdentityDoc, Party, RestartStatus, Run, RunSummary, Selection } from './types'

const DEFAULT: Selection = { issuer: 'certify_preauth', wallet: 'playground_wallet', verifier: 'inji_verify', format: 'ldp_vc', scenario: 'none' }
const LIVE = new Set(['running', 'waiting'])

export default function App() {
  const [tab, setTab] = useState<'bench' | 'report'>('bench')
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [selection, setSelection] = useState<Selection>(DEFAULT)
  const [compat, setCompat] = useState<Compatibility | null>(null)
  const [run, setRun] = useState<Run | null>(null)
  const [history, setHistory] = useState<RunSummary[]>([])
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [subject, setSubject] = useState<IdentityDoc | null>(null)
  const [restart, setRestart] = useState<RestartStatus | null>(null)

  const refreshHistory = useCallback(() => api.history().then(setHistory).catch(() => {}), [])

  useEffect(() => {
    api.catalog().then(setCatalog).catch((e: Error) => setError(`Can't reach the Playground BFF: ${e.message}`))
    // open on the latest run, so the bench shows a real result from the first second
    api.history().then((h) => {
      setHistory(h)
      if (!h[0]) return
      api.run(h[0].id).then((r) => {
        setRun(r)
        setSelection({ issuer: r.issuer, wallet: r.wallet, verifier: r.verifier, format: r.format, scenario: r.scenario })
      }).catch(() => {})
    }).catch(() => {})
  }, [])

  useEffect(() => {
    const load = () => api.health().then(setHealth).catch(() => setHealth(null))
    load()
    const t = setInterval(load, 20000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    api.identity().then((d) => { setSubject(d); setRestart(d.restart) }).catch(() => {})
  }, [])

  // after a save, Certify restarts; watch it until it's serving again
  useEffect(() => {
    if (!restart?.restarting) return
    const t = setInterval(() => {
      api.identityStatus().then((s) => {
        setRestart(s)
        if (!s.restarting) {
          api.identity().then(setSubject).catch(() => {})
          api.health().then(setHealth).catch(() => {})
        }
      }).catch(() => {})
    }, 3000)
    return () => clearInterval(t)
  }, [restart?.restarting])

  async function saveSubject(fields: Record<string, string>) {
    try {
      const d = await api.saveIdentity(fields)
      setSubject(d)
      setRestart(d.restart)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const needsCertify = selection.issuer === 'certify' || selection.wallet === 'inji_web'
  const waitingForCertify = !!restart?.restarting && needsCertify

  useEffect(() => {
    api.compatibility(selection).then(setCompat).catch(() => setCompat(null))
  }, [selection])

  const live = !!run && LIVE.has(run.status)
  useEffect(() => {
    if (!run || !live) return
    const t = setInterval(() => {
      api.run(run.id).then((r) => {
        setRun(r)
        if (!LIVE.has(r.status)) refreshHistory()
      }).catch(() => {})
    }, run.status === 'waiting' ? 2000 : 900)
    return () => clearInterval(t)
  }, [run?.id, run?.status, live, refreshHistory])

  async function start() {
    setStarting(true)
    setError(null)
    try {
      setRun(await api.startRun(selection))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setStarting(false)
    }
  }

  async function act(fn: (id: string) => Promise<Run>) {
    if (!run) return
    try {
      setRun(await fn(run.id))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function open(id: string) {
    try {
      const r = await api.run(id)
      setRun(r)
      setSelection({ issuer: r.issuer, wallet: r.wallet, verifier: r.verifier, format: r.format, scenario: r.scenario })
      setTab('bench')
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const names = useMemo<Partial<Record<Party, string>>>(() => {
    if (!catalog || !run) return {}
    return {
      issuer: catalog.issuers[run.issuer]?.name,
      auth_server: 'eSignet (Collab mock)',
      wallet: catalog.wallets[run.wallet]?.name,
      relying_party: 'Relying party (Playground)',
      verifier: catalog.verifiers[run.verifier]?.name,
      playground: 'Playground',
    }
  }, [catalog, run])

  return (
    <div className="min-h-full">
      <Header health={health} tab={tab} onTab={(t) => { setTab(t); if (t === 'report') refreshHistory() }} />
      <main className="mx-auto flex max-w-[92rem] flex-col gap-5 px-4 py-6 sm:px-6">
        {error && (
          <div role="alert" className="flex items-start justify-between gap-3 rounded-xl px-4 py-3 text-[0.85rem]" style={{ background: 'var(--fail-soft)', color: 'var(--fail)' }}>
            <span>{error}</span>
            <button type="button" onClick={() => setError(null)} className="font-semibold">Dismiss</button>
          </div>
        )}

        {!catalog ? (
          <p className="py-20 text-center text-muted">{error ? 'Start the BFF with python playground/bff/main.py, then reload.' : 'Loading…'}</p>
        ) : tab === 'report' ? (
          <ReportView runs={history} catalog={catalog} onOpen={open} onClear={() => api.clearHistory().then(refreshHistory)} onRefresh={refreshHistory} />
        ) : (
          <>
            <RoleSelector catalog={catalog} selection={selection} onChange={setSelection} locked={live} />
            <SubjectCard doc={subject} format={selection.format} onSave={saveSubject}
              onReload={() => api.reloadEsignet().then(setRestart).catch((e: Error) => setError(e.message))}
              restarting={!!restart?.restarting} pending={!!restart?.esignet_pending} elapsed={restart?.elapsed ?? 0} />
            <RunControls catalog={catalog} selection={selection} onChange={setSelection} compat={compat}
              onRun={start} busy={starting} locked={live} waitingForCertify={waitingForCertify} />
            <div className="grid min-w-0 items-start gap-5 xl:grid-cols-[minmax(22rem,27rem)_1fr]">
              {run ? (
                <RunPanel run={run} catalog={catalog} onContinue={() => act(api.continueRun)} onCancel={() => act(api.cancelRun)} />
              ) : (
                <section className="rounded-2xl border border-dashed border-line-strong p-6 text-[0.85rem] text-muted">
                  <h2 className="font-display text-base font-semibold text-ink">No runs yet</h2>
                  <p className="mt-1">
                    Pick who plays each role, choose a format, and press Run. The issuer issues over OpenID4VCI, the wallet
                    stores the credential and presents it over OpenID4VP, and the verifier's answer is checked against what
                    the standards expect.
                  </p>
                </section>
              )}
              <Inspector steps={run?.steps ?? []} names={names} live={live} />
            </div>
          </>
        )}
      </main>
    </div>
  )
}
