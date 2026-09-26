async function req(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`${method} ${url}: ${res.status} ${await res.text()}`)
  return res.json()
}

const qs = (params) =>
  Object.entries(params)
    .filter(([, v]) => v !== '' && v !== undefined && v !== null && v !== false)
    .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
    .join('&')

export const api = {
  meta: () => req('GET', '/api/meta'),
  dashboard: () => req('GET', '/api/dashboard'),
  graph: () => req('GET', '/api/graph'),
  alerts: () => req('GET', '/api/alerts'),
  alert: (id) => req('GET', `/api/alerts/${id}`),
  inject: () => req('POST', '/api/alerts/inject'),
  resetAlerts: () => req('POST', '/api/alerts/reset'),
  queue: (params) => req('GET', `/api/queue?${qs(params)}`),
  autoLane: () => req('GET', '/api/queue/auto'),
  caseDetail: (id) => req('GET', `/api/cases/${id}`),
  event: (id, ev) => req('POST', `/api/cases/${id}/events`, ev),
  triage: (intake) => req('POST', '/api/triage', intake),
  replay: () => req('GET', '/api/replay'),
  planner: () => req('GET', '/api/planner'),
  resetDemo: () => req('POST', '/api/demo/reset'),
}
