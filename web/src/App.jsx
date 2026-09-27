import React, { useEffect, useState, useCallback, useMemo } from 'react'
import { api } from './api.js'
import { initAuth, login, logout, callbackUrl } from './auth.js'
import { Session } from './session.js'
import Dashboard from './views/Dashboard.jsx'
import Queue from './views/Queue.jsx'
import Intake from './views/Intake.jsx'
import Replay from './views/Replay.jsx'
import Assistant from './components/Assistant.jsx'
import useCardGlow from './useCardGlow.js'

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
  useCardGlow()
  const [boot, setBoot] = useState({ state: 'loading' })
  useEffect(() => {
    (async () => {
      let config
      try {
        config = await api.config()
        const auth = await initAuth(config.auth)
        if (!auth.authenticated) return setBoot({ state: 'login', config, error: auth.error })
        const user = await api.me()
        setBoot({ state: 'ready', config, user })
      } catch (e) {
        if (e.status === 401 && config?.auth?.enabled) {
          // Logged in at Auth0, but our API rejected the token: almost always an audience or domain mismatch.
          return setBoot({ state: 'login', config, error: { code: 'token_rejected', description: e.message } })
        }
        setBoot({ state: 'error', error: e.message })
      }
    })()
  }, [])
  if (boot.state === 'loading') return <div className="spinner">Loading…</div>
  if (boot.state === 'error') return <div className="spinner">Couldn’t reach the API: {boot.error}</div>
  if (boot.state === 'login') return <Login error={boot.error} />
  return <Shell config={boot.config} user={boot.user} />
}

// Plain-language hints for the Auth0 errors people actually hit while setting up.
function hint(err) {
  const d = `${err.code} ${err.description}`.toLowerCase()
  if (d.includes('service not found') || d.includes('audience'))
    return 'AUTH_AUDIENCE must equal the Identifier of your Auth0 API (Applications → APIs), character for character.'
  if (d.includes('callback') || d.includes('redirect'))
    return `Add ${callbackUrl()} to Allowed Callback URLs, Allowed Logout URLs and Allowed Web Origins in the Auth0 application settings.`
  if (d.includes('unauthorized') || d.includes('unknown client') || d.includes('client'))
    return 'Check AUTH_CLIENT_ID, and that the Auth0 application type is “Single Page Application”.'
  if (err.code === 'token_rejected')
    return 'Auth0 login worked, but the API refused the token. Check AUTH_AUDIENCE (API Identifier) and AUTH_DOMAIN in .env, then restart the server.'
  if (err.code === 'access_denied')
    return 'Access was denied: check that the user is allowed to use this application (and AUTH_AUDIENCE).'
  return 'Run `python -m api.auth_check` on the server for a step-by-step diagnosis.'
}

function Login({ error }) {
  return (
    <main className="login">
      <div className="card" style={{ maxWidth: 480 }}>
        <div className="brand" style={{ marginBottom: 12 }}><div className="brand-mark">N</div><span>Northwind Triage</span></div>
        <h2>Sign in to continue</h2>
        <p className="ink2">Complaint records identify customers, so this deployment requires a login.
          Your role (viewer, agent, lead or analyst) decides what you can change.</p>
        {error && (
          <div className="callout" role="alert" style={{ borderColor: 'var(--critical)', marginBottom: 12 }}>
            <div>
              <b>Sign-in failed:</b> {error.code}{error.description ? `: ${error.description}` : ''}
              <div className="small" style={{ marginTop: 6 }}>{hint(error)}</div>
            </div>
          </div>
        )}
        <button className="btn primary" onClick={login}>{error ? 'Try again' : 'Sign in'}</button>
        <div className="small muted" style={{ marginTop: 12 }}>
          Setting up? This page’s callback URL is <code>{callbackUrl()}</code>. It must be listed in the Auth0 application’s
          Allowed Callback URLs, Logout URLs and Web Origins.
        </div>
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
