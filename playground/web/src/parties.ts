import type { Party, Phase } from './types'

// One hue per role, used by the selector, the inspector and the sequence diagram alike.
export const PARTIES: Record<Party, { label: string; short: string; color: string; soft: string }> = {
  issuer: { label: 'Issuer', short: 'Issuer', color: 'var(--issuer)', soft: 'var(--issuer-soft)' },
  auth_server: { label: 'Auth server (eSignet)', short: 'eSignet', color: 'var(--issuer)', soft: 'var(--issuer-soft)' },
  wallet: { label: 'Wallet', short: 'Wallet', color: 'var(--wallet)', soft: 'var(--wallet-soft)' },
  relying_party: { label: 'Relying party (Playground)', short: 'RP', color: 'var(--verifier)', soft: 'var(--verifier-soft)' },
  verifier: { label: 'Verifier', short: 'Verifier', color: 'var(--verifier)', soft: 'var(--verifier-soft)' },
  playground: { label: 'Playground', short: 'Playground', color: 'var(--muted)', soft: 'var(--neutral-soft)' },
}

export const PHASES: { id: Phase; label: string; protocol: string }[] = [
  { id: 'issue', label: 'Issue', protocol: 'OpenID4VCI' },
  { id: 'hold', label: 'Hold', protocol: 'Wallet storage' },
  { id: 'present', label: 'Present', protocol: 'OpenID4VP' },
  { id: 'verify', label: 'Verify', protocol: 'Verifier + own checks' },
]

export function party(p: Party | null | undefined) {
  return PARTIES[p ?? 'playground'] ?? PARTIES.playground
}
