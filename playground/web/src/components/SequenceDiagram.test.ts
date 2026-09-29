import { describe, expect, it } from 'vitest'
import type { Step } from '../types'
import { toMermaid } from './SequenceDiagram'

const step = (over: Partial<Step>): Step => ({
  seq: 1, name: 'Request the credential', phase: 'issue', from: 'wallet', to: 'issuer',
  method: 'POST', url: 'http://x', status: 200, ok: true, ...over,
})

describe('toMermaid', () => {
  it('declares only the parties that take part, in a fixed order', () => {
    const src = toMermaid([step({})], { issuer: 'Inji Certify', wallet: 'Playground wallet' })
    expect(src).toContain('participant I as Inji Certify')
    expect(src).toContain('participant W as Playground wallet')
    expect(src).not.toContain('participant V')
    expect(src.indexOf('participant I')).toBeLessThan(src.indexOf('participant W'))
  })

  it('draws a request and its answer, and a cross for a failed call', () => {
    expect(toMermaid([step({})], {})).toContain('W->>I: 1. Request the credential\n  I-->>W: 200')
    expect(toMermaid([step({ ok: false, status: 401 })], {})).toContain('I--xW: 401')
  })

  it('turns local work into a note', () => {
    expect(toMermaid([step({ method: 'LOCAL', to: 'wallet', name: 'Wallet stores it' })], {}))
      .toContain('Note over W: 1. Wallet stores it')
  })

  it('strips characters that would break the diagram grammar', () => {
    const src = toMermaid([step({ name: 'Verifier: fetch #result; {v2}' })], {})
    expect(src).toContain('1. Verifier fetch result v2')
  })
})
