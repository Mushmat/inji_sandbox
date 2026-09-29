import { describe, expect, it } from 'vitest'
import { decodeJwt } from './JsonView'

const b64url = (o: object) => btoa(JSON.stringify(o)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')

describe('decodeJwt', () => {
  it('decodes the header and payload of a compact JWT', () => {
    const jwt = `${b64url({ alg: 'ES256', typ: 'openid4vci-proof+jwt' })}.${b64url({ nonce: 'n-1', aud: 'http://certify' })}.sig`
    expect(decodeJwt(jwt)).toEqual({ header: { alg: 'ES256', typ: 'openid4vci-proof+jwt' }, payload: { nonce: 'n-1', aud: 'http://certify' } })
  })

  it('leaves ordinary strings alone', () => {
    expect(decodeJwt('did:web:mushmat.github.io:inji_sandbox')).toBeNull()
    expect(decodeJwt('not.a.jwt')).toBeNull()
  })
})
