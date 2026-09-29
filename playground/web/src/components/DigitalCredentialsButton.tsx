import { useState } from 'react'
import { api } from '../api'
import type { Run } from '../types'

// FR13: OpenID4VP through the browser's Digital Credentials API. The browser, not this page,
// talks to the wallets: on a phone it lists the wallet apps, on a desktop it offers to use a phone.
const supported = typeof window !== 'undefined' && 'DigitalCredential' in window && !!navigator.credentials

type DigitalCredential = { protocol: string; data: unknown }

export function DigitalCredentialsButton({ run }: { run: Run }) {
  const [state, setState] = useState<'idle' | 'asking' | 'sent'>('idle')
  const [problem, setProblem] = useState<string | null>(null)

  async function ask() {
    setProblem(null)
    setState('asking')
    try {
      const prepared = await api.dcApiRequest(run.id, window.location.origin)
      const a = prepared.awaiting!
      const credential = (await navigator.credentials.get({
        // The typings don't know the Digital Credentials API yet.
        digital: { requests: a.requests },
        mediation: 'required',
      } as unknown as CredentialRequestOptions)) as unknown as DigitalCredential | null
      if (!credential) throw new Error('No wallet answered.')
      await api.dcApiAnswer(a.response_url!, credential.protocol, credential.data)
      setState('sent')
    } catch (e) {
      const err = e as Error
      setProblem(err.name === 'NotAllowedError' ? 'The request was dismissed, or no wallet on this device can answer it.'
        : err.name === 'NotSupportedError' ? "This browser can't make Digital Credentials API requests."
        : err.message)
      setState('idle')
    }
  }

  return (
    <div className="mt-3 flex flex-col gap-2">
      <p className="text-[0.78rem]" style={{ color: supported ? 'var(--ok)' : 'var(--warn)' }}>
        {supported ? 'This browser supports the Digital Credentials API.'
          : "This browser doesn't expose the Digital Credentials API. Try a recent Chrome or Edge."}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" onClick={ask} disabled={!supported || state !== 'idle'}
          className="rounded-lg px-4 py-2 text-[0.85rem] font-semibold disabled:opacity-45"
          style={{ background: 'var(--wallet)', color: 'var(--surface)' }}>
          {state === 'asking' ? 'Waiting for a wallet…' : state === 'sent' ? 'Answer sent, verifying…' : 'Ask a wallet on this device'}
        </button>
      </div>
      {problem && <p className="text-[0.78rem]" style={{ color: 'var(--fail)' }}>{problem}</p>}
    </div>
  )
}
