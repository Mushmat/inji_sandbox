export type FormatId = 'ldp_vc' | 'vc+sd-jwt' | 'mso_mdoc'
export type ScenarioId = 'none' | 'altered' | 'replay' | 'wrong_type' | 'forged_issuer' | 'expired'
export type Phase = 'issue' | 'hold' | 'present' | 'verify'
export type Party = 'issuer' | 'auth_server' | 'wallet' | 'relying_party' | 'verifier' | 'playground'

export interface RoleOption {
  name: string
  inji: boolean
  version: string | null
  protocol: string
  detail: string
  formats?: FormatId[]
  receive?: FormatId[]
  present?: FormatId[]
  interactive?: boolean
}

export interface Catalog {
  issuers: Record<string, RoleOption>
  wallets: Record<string, RoleOption>
  verifiers: Record<string, RoleOption>
  formats: Record<FormatId, { label: string; short: string; spec: string }>
  scenarios: Record<ScenarioId, { label: string; expected: string; tamper: boolean }>
  versions: Record<string, string>
}

export interface Selection {
  issuer: string
  wallet: string
  verifier: string
  format: FormatId
  scenario: ScenarioId
}

export interface Compatibility {
  runnable: boolean
  blockers: string[]
  limits: string[]
}

export interface Step {
  seq: number
  name: string
  phase: Phase
  from: Party | null
  to: Party | null
  method: string
  url: string | null
  status: number | null
  ok: boolean | null
  request?: unknown
  response?: unknown
  note?: string
  proof_jwt_decoded?: unknown
}

export interface Check {
  id: string
  label: string
  ok: boolean | null
  detail?: string
}

export interface Outcome {
  expected: string
  result: string
  verdict: 'PASS' | 'FAIL' | 'ERROR' | 'UNSUPPORTED'
  explanation?: string
}

export interface Gap {
  summary: string
  failed_checks: string[]
  finding: string[] | null
}

export interface Awaiting {
  kind: 'inji_web_issue' | 'inji_web_present' | 'dc_api'
  title: string
  link: string
  instructions: string[]
  qr?: string | null
  request_uri?: string | null
  request_id?: string
  response_url?: string
  requests?: { protocol: string; data: unknown }[]
}

export interface RestartStatus {
  restarting: boolean
  healthy: boolean
  elapsed: number
  stuck: boolean
  error: string | null
  esignet_pending: boolean
}

export interface IdentityDoc {
  individual_id: string
  fields: string[]
  identity: Record<string, string>
  restart: RestartStatus
}

export interface Run {
  id: string
  created_at: string
  finished_at: string | null
  duration_ms: number | null
  status: 'running' | 'waiting' | 'done' | 'error' | 'cancelled'
  phase: Phase | 'done'
  issuer: string
  wallet: string
  verifier: string
  format: FormatId
  scenario: ScenarioId
  versions: Record<string, string>
  compat: Compatibility
  credential: Record<string, unknown> | null
  proof_type: string | null
  outcome: Outcome | null
  verifier_result: { status?: string; detail?: string; checks?: Check[] } | null
  playground_checks: Check[]
  suspected_gaps: Gap[]
  unsupported: string | null
  awaiting: Awaiting | null
  error: string | null
  timings?: { issue_ms?: number; present_verify_ms?: number }
  steps: Step[]
}

export type RunSummary = Omit<Run, 'steps' | 'compat' | 'credential' | 'verifier_result' | 'playground_checks' | 'awaiting'>

export interface Health {
  services: { id: string; label: string; url: string; up: boolean; detail: string }[]
  did: { ok: boolean; detail: string }
}

export interface MatrixState {
  running: boolean
  preset: 'quick' | 'full' | null
  total: number
  done: number
  current: Pick<Selection, 'issuer' | 'wallet' | 'verifier' | 'format' | 'scenario'> | null
  run_ids: string[]
  started_at: string | null
  finished_at: string | null
  cancelled: boolean
  error: string | null
  sizes: { quick: number; full: number }
}
