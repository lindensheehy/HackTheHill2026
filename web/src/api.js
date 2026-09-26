import { token } from './auth.js'

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail)
    this.status = status
  }
}

async function send(method, url, body) {
  const headers = {}
  if (body) headers['Content-Type'] = 'application/json'
  const t = await token()
  if (t) headers.Authorization = `Bearer ${t}`
  const res = await fetch(url, { method, headers, body: body ? JSON.stringify(body) : undefined })
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail || detail } catch { /* not JSON */ }
    throw new ApiError(res.status, detail)
  }
  return res
}

const req = async (method, url, body) => (await send(method, url, body)).json()
const blob = async (method, url, body) => (await send(method, url, body)).blob()

const qs = (params) =>
  Object.entries(params)
    .filter(([, v]) => v !== '' && v !== undefined && v !== null && v !== false)
    .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
    .join('&')

export const api = {
  config: () => req('GET', '/api/config'),
  me: () => req('GET', '/api/me'),
  meta: () => req('GET', '/api/meta'),
  dashboard: () => req('GET', '/api/dashboard'),
  graph: () => req('GET', '/api/graph'),
  alerts: () => req('GET', '/api/alerts'),
  alert: (id) => req('GET', `/api/alerts/${id}`),
  inject: () => req('POST', '/api/alerts/inject'),
  resetAlerts: () => req('POST', '/api/alerts/reset'),
  brief: (id, force) => req('POST', `/api/assistant/brief/${id}${force ? '?force=true' : ''}`),
  ask: (body) => req('POST', '/api/assistant/ask', body),
  queue: (params) => req('GET', `/api/queue?${qs(params)}`),
  autoLane: () => req('GET', '/api/queue/auto'),
  caseDetail: (id) => req('GET', `/api/cases/${id}`),
  event: (id, ev) => req('POST', `/api/cases/${id}/events`, ev),
  customerUpdate: (id) => req('GET', `/api/cases/${id}/customer-update`),
  customerUpdateAudio: (id) => blob('GET', `/api/cases/${id}/customer-update/audio`),
  tts: (text) => blob('POST', '/api/voice/tts', { text }),
  triage: (intake) => req('POST', '/api/triage', intake),
  replay: () => req('GET', '/api/replay'),
  planner: () => req('GET', '/api/planner'),
  usage: () => req('GET', '/api/usage'),
  resetDemo: () => req('POST', '/api/demo/reset'),
}
