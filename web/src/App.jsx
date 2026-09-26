import React, { useEffect, useState, useCallback, useMemo } from 'react'
import { api } from './api.js'
import { initAuth, login, logout } from './auth.js'
import { Session } from './session.js'
import Dashboard from './views/Dashboard.jsx'
import Queue from './views/Queue.jsx'
import Intake from './views/Intake.jsx'
import Replay from './views/Replay.jsx'
import Assistant from './components/Assistant.jsx'

const TABS = [
  { id: 'dashboard', label: 'Operations' },
  { id: 'intake', label: 'Intake' },
  { id: 'replay', label: 'Replay' },
  { id: 'queue', label: 'Triage queue' },
]

function parseHash() {
  const raw = window.location.hash.replace(/^#\/?/, '')
  const [path, query = ''] = raw.split('?')
  const [tab, ...rest] = path.split('/')
  return {
    tab: TABS.some((t) => t.id === tab) ? tab : 'dashboard',
    arg: decodeURIComponent(rest.join('/')),
    params: Object.fromEntries(new URLSearchParams(query)),
  }
}

function useHash() {
  const [route, setRoute] = useState(parseHash)
  useEffect(() => {
    const on = () => setRoute(parseHash())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return route
}

export const go = (tab, arg, params) => {
  const q = params ? `?${new URLSearchParams(params)}` : ''
  window.location.hash = `/${tab}${arg ? `/${arg}` : ''}${q}`
}

export default function App() {
  const [boot, setBoot] = useState({ state: 'loading' })
  useEffect(() => {
    (async () => {
      try {
        const config = await api.config()
        const auth = await initAuth(config.auth)
        if (!auth.authenticated) return setBoot({ state: 'login', config })
        const user = await api.me()
        setBoot({ state: 'ready', config, user })
      } catch (e) {
        setBoot({ state: 'error', error: e.message })
      }
    })()
  }, [])
  if (boot.state === 'loading') return <div className="spinner">Loading…</div>
  if (boot.state === 'error') return <div className="spinner">Couldn’t reach the API: {boot.error}</div>
  if (boot.state === 'login') return <Login />
  return <Shell config={boot.config} user={boot.user} />
}

function Login() {
  return (
    <main className="login">
      <div className="card" style={{ maxWidth: 440 }}>
        <div className="brand" style={{ marginBottom: 12 }}><div className="brand-mark">N</div><span>Northwind Triage</span></div>
        <h2>Sign in to continue</h2>
        <p className="ink2">Complaint records identify customers, so this deployment requires a login.
          Your role (viewer, agent, lead or analyst) decides what you can change.</p>
        <button className="btn primary" onClick={login}>Sign in</button>
      </div>
    </main>
  )
}

function Shell({ config, user }) {
  const { tab, arg, params } = useHash()
  const [meta, setMeta] = useState(null)
  const [activeAlerts, setActiveAlerts] = useState(0)
  const [focus, setFocusState] = useState({})
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem('nw-theme') || '' } catch { return '' }
  })
  const can = useCallback((perm) => user.permissions.includes(perm), [user])
  const setFocus = useCallback((f) => setFocusState(f || {}), [])

  useEffect(() => { api.meta().then(setMeta) }, [])
  const refreshAlerts = useCallback(() => {
    api.alerts().then((d) => setActiveAlerts(d.alerts.filter((a) => a.status === 'active').length))
  }, [])
  useEffect(refreshAlerts, [refreshAlerts, tab])
  useEffect(() => { setFocus({}) }, [tab, setFocus])
  useEffect(() => {
    if (theme) document.documentElement.setAttribute('data-theme', theme)
    else document.documentElement.removeAttribute('data-theme')
    try { localStorage.setItem('nw-theme', theme) } catch { /* private mode */ }
  }, [theme])

  const session = useMemo(() => ({ config, user, can, focus, setFocus }), [config, user, can, focus, setFocus])

  const resetDemo = async () => {
    if (!confirm('Clear demo complaints, case events and simulated alerts?')) return
    await api.resetDemo()
    window.location.reload()
  }

  return (
    <Session.Provider value={session}>
      <a href="#main" className="skip">Skip to content</a>
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark" aria-hidden>N</div>
          <span>Northwind Triage</span>
        </div>
        <nav className="tabs" aria-label="Sections">
          {TABS.map((t) => (
            <button key={t.id} className={`tab ${tab === t.id ? 'active' : ''}`} onClick={() => go(t.id)}
              aria-current={tab === t.id ? 'page' : undefined}>
              {t.label}
              {t.id === 'dashboard' && activeAlerts > 0 && <span className="badge" aria-label={`${activeAlerts} active alerts`}>{activeAlerts}</span>}
            </button>
          ))}
        </nav>
        <div className="spacer" />
        <span className="asof">Data as of {config.as_of}</span>
        {user.auth && (
          <span className="chip" title={user.permissions.join(', ')}>{user.name} · {user.role}</span>
        )}
        <button className="btn sm" onClick={() => setTheme(theme === 'dark' ? 'light' : theme === 'light' ? '' : 'dark')}
          title="Theme: follows system / dark / light">
          {theme === 'dark' ? 'Dark' : theme === 'light' ? 'Light' : 'Auto'}
        </button>
        {can('demo:reset') && <button className="btn sm" onClick={resetDemo} title="Reset demo state">Reset</button>}
        {user.auth && <button className="btn sm" onClick={logout}>Sign out</button>}
      </header>
      <main id="main">
        {tab === 'dashboard' && <Dashboard onAlertsChanged={refreshAlerts} alertArg={arg} />}
        {tab === 'intake' && <Intake meta={meta} />}
        {tab === 'replay' && <Replay />}
        {tab === 'queue' && <Queue meta={meta} highlight={arg} params={params} />}
      </main>
      <Assistant page={tab} />
    </Session.Provider>
  )
}
