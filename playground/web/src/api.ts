import type { Catalog, Compatibility, Health, IdentityDoc, MatrixState, RestartStatus, Run, RunSummary, Selection } from './types'

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') message = body.detail
      else if (body.detail?.message) message = body.detail.message
    } catch {
      // not JSON; keep the status line
    }
    throw new Error(message)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

export const api = {
  health: () => call<Health>('/api/health'),
  catalog: () => call<Catalog>('/api/catalog'),
  compatibility: (s: Selection) => call<Compatibility>('/api/compatibility', { method: 'POST', body: JSON.stringify(s) }),
  startRun: (s: Selection) => call<Run>('/api/runs', { method: 'POST', body: JSON.stringify(s) }),
  run: (id: string) => call<Run>(`/api/runs/${id}`),
  continueRun: (id: string) => call<Run>(`/api/runs/${id}/continue`, { method: 'POST' }),
  cancelRun: (id: string) => call<Run>(`/api/runs/${id}/cancel`, { method: 'POST' }),
  dcApiRequest: (id: string, origin: string) => call<Run>(`/api/runs/${id}/dc-api`, { method: 'POST', body: JSON.stringify({ origin }) }),
  dcApiAnswer: (url: string, protocol: string, data: unknown) =>
    call<unknown>(url, { method: 'POST', body: JSON.stringify({ protocol, data }) }),
  history: () => call<RunSummary[]>('/api/runs'),
  clearHistory: () => call<void>('/api/runs', { method: 'DELETE' }),
  identity: () => call<IdentityDoc>('/api/identity'),
  saveIdentity: (fields: Record<string, string>) =>
    call<IdentityDoc>('/api/identity', { method: 'PUT', body: JSON.stringify({ fields }) }),
  identityStatus: () => call<RestartStatus>('/api/identity/status'),
  reloadEsignet: () => call<RestartStatus>('/api/identity/reload', { method: 'POST' }),
  matrix: () => call<MatrixState>('/api/matrix'),
  startMatrix: (preset: 'quick' | 'full') => call<MatrixState>('/api/matrix', { method: 'POST', body: JSON.stringify({ preset }) }),
  cancelMatrix: () => call<MatrixState>('/api/matrix/cancel', { method: 'POST' }),
}
