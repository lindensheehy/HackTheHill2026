import React, { useState } from 'react'
import { api } from '../api.js'
import { Card, Loading } from '../components/common.jsx'
import { useSession } from '../session.js'
import TriageCard from '../components/TriageCard.jsx'
import { int } from '../format.js'

const BLANK = { channel: 'Phone', category: 'Billing - disputed amount', priority: 'P3', region: 'Ashford', account_id: '', entry_system: '' }

export default function Intake({ meta }) {
  const { can } = useSession()
  const [form, setForm] = useState(BLANK)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  if (!meta) return <Loading />

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const submit = async (intake = form) => {
    setBusy(true)
    setErr(null)
    try {
      const body = { ...intake }
      if (!body.account_id) delete body.account_id
      if (!body.entry_system) delete body.entry_system
      setResult(await api.triage(body))
    } catch (e) {
      setErr(String(e))
    }
    setBusy(false)
  }
  const useExample = (ex) => {
    const f = { ...BLANK, ...ex.intake }
    setForm(f)
    submit(f)
  }
  const entryDefault = meta.channel_entry[form.channel]

  return (
    <div className="stack">
      <div>
        <h2>Intake simulator</h2>
        <div className="ink2">An agent's intake screen. The router decides the owner <b>once, at intake</b>, and the case goes straight into the triage queue.</div>
      </div>
      <div className="grid g-side">
        <div className="stack">
          <Card title="New complaint">
            <form className="stack" style={{ gap: 12 }} onSubmit={(e) => { e.preventDefault(); submit() }}>
              <label className="field">Channel
                <select value={form.channel} onChange={set('channel')}>{meta.channels.map((c) => <option key={c}>{c}</option>)}</select>
              </label>
              <label className="field">Arrived in system
                <select value={form.entry_system} onChange={set('entry_system')}>
                  <option value="">Default for channel ({entryDefault})</option>
                  {meta.entry_systems.map((s) => <option key={s.id} value={s.id}>{s.id} {s.name}</option>)}
                </select>
              </label>
              <label className="field">Category
                <select value={form.category} onChange={set('category')}>{meta.categories.map((c) => <option key={c}>{c}</option>)}</select>
              </label>
              <div className="grid g2" style={{ gap: 12 }}>
                <label className="field">Priority
                  <select value={form.priority} onChange={set('priority')}>
                    {meta.priorities.map((p) => <option key={p} value={p}>{p} · {meta.sla_days[p]}-day SLA</option>)}
                  </select>
                </label>
                <label className="field">Region
                  <select value={form.region} onChange={set('region')}>{meta.regions.map((c) => <option key={c}>{c}</option>)}</select>
                </label>
              </div>
              <label className="field">Account (optional)
                <input type="text" placeholder="ACC-000000" value={form.account_id} onChange={set('account_id')} />
              </label>
              <button className="btn primary" disabled={busy || !can('intake:create')} title={can('intake:create') ? '' : 'Your role can’t create complaints'}>
                {busy ? 'Routing…' : 'Route complaint'}</button>
              {err && <div className="small" style={{ color: 'var(--critical)' }}>{err}</div>}
            </form>
          </Card>
          <Card title="Prepared examples">
            <div className="stack" style={{ gap: 8 }}>
              {meta.examples.map((ex) => (
                <button key={ex.title} className="btn" style={{ textAlign: 'left', whiteSpace: 'normal' }} onClick={() => useExample(ex)} disabled={busy || !can('intake:create')}>
                  <div style={{ fontWeight: 600 }}>{ex.title}</div>
                  <div className="small ink2">{ex.blurb}</div>
                </button>
              ))}
            </div>
            <div className="small muted" style={{ marginTop: 10 }}>
              Tip: inject the scenario on the Operations tab first, and the Barrowdale example picks up the regional alert.
            </div>
          </Card>
        </div>
        <div>
          {!result ? (
            <Card><div className="empty">Submit a complaint to see the triage card.</div></Card>
          ) : (
            <div className="stack" style={{ gap: 12 }}>
              <div className="callout info">
                <div style={{ flex: 1 }}>
                  <b>{result.complaint_id}</b> created in CaseTrack.{' '}
                  {result.in_auto_lane
                    ? <>High information-only likelihood: it went to the <b>auto-answer lane</b> with a 7-day watch.</>
                    : <>It sits at <b>#{int(result.queue_rank)}</b> of {int(result.queue_size)} in the triage queue.</>}
                </div>
                <a className="btn sm primary" style={{ textDecoration: 'none' }}
                  href={result.in_auto_lane ? '#/queue/auto' : `#/queue/${result.complaint_id}`}>
                  {result.in_auto_lane ? 'Open auto lane →' : 'See it in the queue →'}
                </a>
              </div>
              <TriageCard t={result} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
