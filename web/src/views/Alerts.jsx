import React, { useEffect, useState } from 'react'
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine } from 'recharts'
import { api } from '../api.js'
import { Card, Loading, Tip, Legend, Pri, Overdue, axisProps } from '../components/common.jsx'
import { num, int, monthLabel } from '../format.js'

const SERIES = ['var(--s1)', 'var(--s2)', 'var(--s3)']

export default function Alerts({ onChanged, initial }) {
  const [alerts, setAlerts] = useState(null)
  const [scenario, setScenario] = useState(null)
  const [showHistory, setShowHistory] = useState(false)
  const [sel, setSel] = useState(initial || null)
  const [busy, setBusy] = useState(false)

  const load = () => api.alerts().then((d) => {
    setAlerts(d.alerts)
    setScenario(d.scenario)
    const top = d.alerts.filter((a) => a.status === 'active').sort((a, b) => b.z - a.z)[0]
    setSel((cur) => cur || top?.alert_id || null)
  })
  useEffect(() => { load() }, [])

  const inject = async () => {
    setBusy(true)
    const r = await api.inject()
    await load()
    const top = [...r.alerts].sort((a, b) => b.z - a.z)[0]
    setSel(top?.alert_id)
    setBusy(false)
    onChanged()
  }
  const reset = async () => {
    await api.resetAlerts()
    await load()
    setSel(null)
    onChanged()
  }

  if (!alerts) return <Card><Loading /></Card>
  const active = alerts.filter((a) => a.status === 'active')
  const history = alerts.filter((a) => a.status !== 'active')
  const hasSim = alerts.some((a) => a.synthetic)
  const list = showHistory ? [...active, ...history] : active

  return (
    <div className="grid g-5-7">
      <Card title={`Alerts feed · ${active.length} active`}
        sub={`${history.length} historical alerts over two years (z ≥ 3 or CUSUM drift)`}
        right={<div className="row">
          {hasSim ? <button className="btn sm" onClick={reset}>Clear simulation</button>
            : <button className="btn sm primary" onClick={inject} disabled={busy}>{busy ? 'Detecting…' : 'Inject scenario'}</button>}
        </div>}>
        {!hasSim && scenario && (
          <div className="callout info small" style={{ marginBottom: 10 }}>
            <div><b>Simulated feed:</b> {scenario.description} The same detector that runs on real data will pick it up.</div>
          </div>
        )}
        {active.length === 0 && <div className="muted small" style={{ padding: '6px 2px 10px' }}>
          Quiet: no signal is currently outside its normal range. Real spikes in this data are modest (no category peaks above ~1.5× its average).
        </div>}
        <div style={{ maxHeight: 380, overflowY: 'auto' }}>
          {list.map((a) => (
            <div key={a.alert_id} className={`alert-item ${sel === a.alert_id ? 'sel' : ''}`} onClick={() => setSel(a.alert_id)}>
              <div className="sev" style={{ background: a.status === 'active' ? (a.z >= 5 ? 'var(--critical)' : 'var(--serious)') : 'var(--axis)' }} />
              <div style={{ minWidth: 0 }}>
                <div className="row" style={{ gap: 6 }}>
                  {a.synthetic ? <span className="sim-tag">simulated</span> : null}
                  <span className="muted small">{monthLabel(a.month)} · {a.detail.method === 'cusum' ? 'CUSUM drift' : `z = ${num(a.z)}`}</span>
                </div>
                <div style={{ fontWeight: a.status === 'active' ? 600 : 400 }}>{a.detail.summary}</div>
              </div>
            </div>
          ))}
        </div>
        <button className="btn sm" style={{ marginTop: 8 }} onClick={() => setShowHistory(!showHistory)}>
          {showHistory ? 'Hide history' : `Show history (${history.length})`}
        </button>
      </Card>
      {sel ? <Investigation id={sel} key={sel} /> : (
        <Card title="Investigation">
          <div className="empty">Select an alert, or inject the scenario to watch the pipeline detect and connect it.</div>
        </Card>
      )}
    </div>
  )
}

function Investigation({ id }) {
  const [d, setD] = useState(null)
  useEffect(() => { api.alert(id).then(setD).catch(() => setD(false)) }, [id])
  if (d === false) return <Card title="Investigation"><div className="empty">Alert no longer exists.</div></Card>
  if (!d) return <Card title="Investigation"><Loading /></Card>
  const a = d.alert
  const regions = Object.keys(d.series)
  const months = [...new Set(regions.flatMap((r) => d.series[r].map((p) => p.month)))].sort().slice(-12)
  const data = months.map((m) => {
    const row = { month: m, label: monthLabel(m) }
    regions.forEach((r) => { const p = d.series[r].find((x) => x.month === m); row[r] = p?.v })
    return row
  })
  const isRate = a.signal.endsWith('_rate')
  const f = (v) => (v == null ? '–' : isRate ? `${(v * 100).toFixed(1)}%` : num(v, a.signal.startsWith('complaints') ? 0 : 1))
  return (
    <Card title="Investigation" sub={a.detail.label}
      right={a.synthetic ? <span className="sim-tag">simulated</span> : <span className="muted small">{a.status}</span>}>
      <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 10 }}>{a.detail.summary}</div>
      <div className="row between">
        <h4>{a.detail.label}, last 12 months</h4>
        {regions.length > 1 && <Legend items={regions.map((r, i) => ({ label: r, color: SERIES[i % 3] }))} />}
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={data} margin={{ top: 10, right: 20, bottom: 0, left: -10 }}>
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis dataKey="label" {...axisProps} interval={1} />
          <YAxis {...axisProps} tickFormatter={f} width={50} />
          <ReferenceLine x={monthLabel(a.month)} stroke="var(--critical)" strokeWidth={1} />
          <Tooltip content={({ active, payload }) => active && payload?.length ? (
            <Tip head={payload[0].payload.label} rows={regions.map((r, i) => ({ color: SERIES[i % 3], label: r, value: f(payload[0].payload[r]) }))} />
          ) : null} />
          {regions.map((r, i) => (
            <Line key={r} dataKey={r} stroke={SERIES[i % 3]} strokeWidth={2} isAnimationActive={false}
              dot={{ r: 4, fill: SERIES[i % 3], stroke: 'var(--surface)', strokeWidth: 2 }} />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <div style={{ overflowX: 'auto' }}><table style={{ marginTop: 8 }}>
        <thead><tr><th>Region</th><th className="num">This month</th><th className="num">Trailing avg</th><th className="num">{a.detail.method === 'cusum' ? 'CUSUM' : 'z'}</th></tr></thead>
        <tbody>
          {a.detail.per_region.map((p) => (
            <tr key={p.region}><td>{p.region}</td><td className="num">{f(p.value)}</td><td className="num">{f(p.baseline)}</td><td className="num">{num(p.z)}</td></tr>
          ))}
        </tbody>
      </table></div>
      {a.shared_systems.length > 0 && (
        <>
          <h4 style={{ margin: '14px 0 6px' }}>Systems all affected regions share</h4>
          <div className="stack" style={{ gap: 6 }}>
            {a.detail.system_notes.map((s) => (
              <div className="callout" key={s.system}><div><b>{s.system}</b><div className="ink2 small">{s.note}</div></div></div>
            ))}
          </div>
        </>
      )}
      <h4 style={{ margin: '14px 0 6px' }}>Linked open complaints · {int(d.linked_open_total)}</h4>
      {d.linked_open.length === 0 ? <div className="muted small">None open in the related categories.</div> : (
        <div style={{ overflowX: 'auto' }}><table>
          <tbody>
            {d.linked_open.slice(0, 6).map((r) => (
              <tr key={r.complaint_id} className="click" onClick={() => { window.location.hash = `/queue/${r.complaint_id}` }}>
                <td>{r.complaint_id}</td><td><Pri p={r.priority} /></td><td>{r.region}</td>
                <td className="ink2">{r.category}</td><td><Overdue days={r.overdue_days} state={r.overdue_state} /></td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
    </Card>
  )
}
