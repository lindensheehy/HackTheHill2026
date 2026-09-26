import React, { useEffect, useState, useCallback } from 'react'
import { api } from './api.js'
import Dashboard from './views/Dashboard.jsx'
import Queue from './views/Queue.jsx'
import Intake from './views/Intake.jsx'
import Replay from './views/Replay.jsx'

const TABS = [
  { id: 'dashboard', label: 'Operations' },
  { id: 'intake', label: 'Intake' },
  { id: 'replay', label: 'Replay' },
  { id: 'queue', label: 'Triage queue' },
]

function useHash() {
  const read = () => {
    const [tab, ...rest] = window.location.hash.replace(/^#\/?/, '').split('/')
    return { tab: TABS.some((t) => t.id === tab) ? tab : 'dashboard', arg: rest.join('/') }
  }
  const [route, setRoute] = useState(read)
  useEffect(() => {
    const on = () => setRoute(read())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return route
}

export const go = (tab, arg) => {
  window.location.hash = `/${tab}${arg ? `/${arg}` : ''}`
}

export default function App() {
  const { tab, arg } = useHash()
  const [meta, setMeta] = useState(null)
  const [activeAlerts, setActiveAlerts] = useState(0)
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem('nw-theme') || '' } catch { return '' }
  })

  useEffect(() => { api.meta().then(setMeta) }, [])
  const refreshAlerts = useCallback(() => {
    api.alerts().then((d) => setActiveAlerts(d.alerts.filter((a) => a.status === 'active').length))
  }, [])
  useEffect(refreshAlerts, [refreshAlerts, tab])
  useEffect(() => {
    if (theme) document.documentElement.setAttribute('data-theme', theme)
    else document.documentElement.removeAttribute('data-theme')
    try { localStorage.setItem('nw-theme', theme) } catch { /* private mode */ }
  }, [theme])

  const resetDemo = async () => {
    if (!confirm('Clear demo complaints, case events and simulated alerts?')) return
    await api.resetDemo()
    window.location.reload()
  }

  return (
    <>
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">N</div>
          <span>Northwind Triage</span>
        </div>
        <nav className="tabs">
          {TABS.map((t) => (
            <button key={t.id} className={`tab ${tab === t.id ? 'active' : ''}`} onClick={() => go(t.id)}>
              {t.label}
              {t.id === 'dashboard' && activeAlerts > 0 && <span className="badge">{activeAlerts}</span>}
            </button>
          ))}
        </nav>
        <div className="spacer" />
        <span className="asof">Data as of {meta?.as_of ?? '…'}</span>
        <button className="btn sm" onClick={() => setTheme(theme === 'dark' ? 'light' : theme === 'light' ? '' : 'dark')}
          title="Theme: follows system / dark / light">
          {theme === 'dark' ? 'Dark' : theme === 'light' ? 'Light' : 'Auto'}
        </button>
        <button className="btn sm" onClick={resetDemo} title="Reset demo state">Reset</button>
      </header>
      <main>
        {tab === 'dashboard' && <Dashboard onAlertsChanged={refreshAlerts} alertArg={arg} />}
        {tab === 'intake' && <Intake meta={meta} />}
        {tab === 'replay' && <Replay />}
        {tab === 'queue' && <Queue meta={meta} highlight={arg} />}
      </main>
    </>
  )
}
