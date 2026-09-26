import React, { useEffect, useMemo, useRef, useState } from 'react'
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts'
import { api } from '../api.js'
import { Card, Loading, Tip, Legend, Provenance, axisProps } from '../components/common.jsx'
import { pct, int, gbp, monthLabel } from '../format.js'

const MONTH_MS = 1000   // one month per second

export default function Replay() {
  const [d, setD] = useState(null)
  const [adoption, setAdoption] = useState(0.8)
  const [avoidance, setAvoidance] = useState(0.6)
  const [t, setT] = useState(0)          // progress in months, 0..n
  const [playing, setPlaying] = useState(false)
  const raf = useRef()
  useEffect(() => { api.replay().then((r) => { setD(r); setAdoption(r.defaults.adoption); setAvoidance(r.defaults.avoidance) }) }, [])

  const weeks = useMemo(() => {
    if (!d) return []
    // Flatten to weeks with fractional month positions, so counters climb smoothly.
    return d.months.flatMap((m, mi) => m.weeks.map((w, wi) => ({ ...w, month: m.month, pos: mi + (wi + 1) / m.weeks.length })))
  }, [d])

  useEffect(() => {
    if (!playing || !d) return
    let start
    const from = t >= d.months.length ? 0 : t
    const step = (ts) => {
      if (start == null) start = ts
      const nt = Math.min(d.months.length, from + (ts - start) / MONTH_MS)
      setT(nt)
      if (nt < d.months.length) raf.current = requestAnimationFrame(step)
      else setPlaying(false)
    }
    raf.current = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf.current)
  }, [playing])

  if (!d) return <Loading />

  const k = adoption * avoidance
  const done = weeks.filter((w) => w.pos <= t + 1e-9)
  const complaints = done.reduce((s, w) => s + w.complaints, 0)
  const transfers = done.reduce((s, w) => s + w.transfers, 0)
  const avoided = transfers * k
  const per = d.per_avoided
  const monthIdx = Math.min(d.months.length - 1, Math.floor(t))
  const ticker = t > 0 ? d.months[monthIdx].ticker.slice(0, Math.max(1, Math.round((t - monthIdx) * 24))).reverse().slice(0, 12) : []

  let cumA = 0
  let cumR = 0
  const chart = weeks.map((w) => {
    cumA += w.transfers
    cumR += w.transfers * (1 - k)
    return { week: w.week, label: monthLabel(w.month), actual: w.pos <= t + 1e-9 ? cumA : null, routed: w.pos <= t + 1e-9 ? cumR : null }
  })
  const annual = d.annual_transfers * k
  const yMax = Math.ceil(d.months.reduce((s, m) => s + m.actual_transfers, 0) / 500) * 500

  return (
    <div className="stack">
      <div className="row between">
        <div>
          <h2>Replay: what if we'd had the router?</h2>
          <div className="ink2">The last 6 months of real complaints ({int(d.total_complaints)}, Apr–Sep 2026) replayed through the router at one month per second.</div>
          <div className="callout" style={{ marginTop: 10 }}>
            <Provenance kind="assumption" />
            <div className="small">This is a scenario, not a measured result. It applies the historical difference between transferred and non-transferred
              complaints to the share of transfers you assume routing avoids. The transfer counts are real; the savings depend on the two sliders.</div>
          </div>
        </div>
        <div className="row">
          <button className="btn primary" onClick={() => { if (t >= d.months.length) setT(0); setPlaying(!playing) }}>
            {playing ? 'Pause' : t >= d.months.length ? 'Replay again' : t > 0 ? 'Resume' : '▶ Play'}
          </button>
          <button className="btn" onClick={() => { setPlaying(false); setT(0) }}>Reset</button>
          <button className="btn" onClick={() => { setPlaying(false); setT(d.months.length) }}>Skip to end</button>
        </div>
      </div>

      <div className="grid g-7-5">
        <Card title="Assumptions" sub="Conservative by default; drag to explore">
          <div className="grid g2" style={{ gap: 20 }}>
            <label className="field">Adoption: <b>{pct(adoption)}</b> of complaints enter through the router
              <input type="range" min={0} max={1} step={0.05} value={adoption} onChange={(e) => setAdoption(+e.target.value)} />
            </label>
            <label className="field">Transfer avoidance: <b>{pct(avoidance)}</b> of would-be transfers prevented
              <input type="range" min={0} max={1} step={0.05} value={avoidance} onChange={(e) => setAvoidance(+e.target.value)} />
            </label>
          </div>
          <div className="small muted" style={{ marginTop: 10 }}>
            Per transfer avoided: {gbp(per.gbp)} (Finance cost model: £121 vs £68), {per.days.toFixed(1)} days, {per.reopens.toFixed(3)} reopens, {per.breaches.toFixed(3)} breaches.
          </div>
        </Card>
        <Card title="Annualised at these settings" sub={`${int(d.annual_transfers)} real transfers in the last 12 months × ${pct(k)} assumed avoided`} right={<Provenance kind="assumption" />}>
          <div className="grid g2" style={{ gap: 10 }}>
            <div><div style={{ fontSize: 26, fontWeight: 600 }}>{gbp(annual * per.gbp)}</div><div className="ink2 small">handling cost / yr</div></div>
            <div><div style={{ fontSize: 26, fontWeight: 600 }}>{int(annual * per.days)}</div><div className="ink2 small">complaint-days / yr</div></div>
            <div><div style={{ fontSize: 26, fontWeight: 600 }}>{int(annual * per.reopens)}</div><div className="ink2 small">reopens avoided / yr</div></div>
            <div><div style={{ fontSize: 26, fontWeight: 600 }}>{int(annual * per.breaches)}</div><div className="ink2 small">SLA breaches avoided / yr</div></div>
          </div>
        </Card>
      </div>

      <div className="grid g5">
        <Counter k="Complaints replayed" v={int(complaints)} sub={t > 0 ? monthLabel(d.months[monthIdx].month) : 'not started'} />
        <Counter k="Transfers avoided" v={int(avoided)} sub={`of ${int(transfers)} that happened`} />
        <Counter k="£ saved" v={gbp(avoided * per.gbp)} accent />
        <Counter k="Complaint-days saved" v={int(avoided * per.days)} />
        <Counter k="Reopens avoided" v={int(avoided * per.reopens)} sub={`${int(avoided * per.breaches)} breaches avoided`} />
      </div>

      <div className="grid g-7-5">
        <Card title="Cumulative transfers" right={<Legend items={[{ label: 'What happened', color: 'var(--s2)' }, { label: 'Scenario: with the router', color: 'var(--s1)' }]} />}>
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={chart} margin={{ top: 10, right: 20, bottom: 0, left: -10 }}>
              <CartesianGrid vertical={false} stroke="var(--grid)" />
              <XAxis dataKey="label" {...axisProps} interval={Math.max(1, Math.floor(chart.length / 6))} />
              <YAxis {...axisProps} domain={[0, yMax]} ticks={Array.from({ length: yMax / 500 + 1 }, (_, i) => i * 500)} tickFormatter={int} />
              <Tooltip content={({ active, payload }) => active && payload?.length && payload[0].payload.actual != null ? (
                <Tip head={`Week of ${payload[0].payload.week}`} rows={[
                  { color: 'var(--s2)', label: 'What happened', value: int(payload[0].payload.actual) },
                  { color: 'var(--s1)', label: 'Scenario: with the router', value: int(payload[0].payload.routed) },
                ]} />) : null} />
              <Area dataKey="actual" stroke="var(--s2)" strokeWidth={2} fill="var(--s2)" fillOpacity={0.1} isAnimationActive={false} connectNulls={false} />
              <Area dataKey="routed" stroke="var(--s1)" strokeWidth={2} fill="var(--s1)" fillOpacity={0.1} isAnimationActive={false} connectNulls={false} />
            </AreaChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Router decisions" sub="A sample of the month's complaints as they arrive">
          <div className="ticker">
            {ticker.length === 0 && <div className="empty">Press play.</div>}
            {ticker.map((x) => (
              <div className="tick" key={x.id}>
                <span className="tnum">{x.id}</span>
                <span className="muted">{x.entry} → 04</span>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{x.category}</span>
                <span className="row" style={{ gap: 6, justifyContent: 'flex-end', flexWrap: 'nowrap' }}>
                  {x.transferred && <span className="chip" style={{ background: 'var(--focus-wash)', color: 'var(--ink)' }}>was transferred</span>}
                  <span className="ink2">{x.team}</span>
                </span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}

function Counter({ k, v, sub, accent }) {
  return (
    <Card className="counter">
      <div className="ink2 small">{k}</div>
      <div className="value tnum" style={accent ? { color: 'var(--good-text)' } : undefined}>{v}</div>
      {sub && <div className="muted small">{sub}</div>}
    </Card>
  )
}
