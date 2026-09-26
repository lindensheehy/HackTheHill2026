import React, { useEffect, useMemo, useState } from 'react'
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine } from 'recharts'
import { api } from '../api.js'
import { Card, Loading, Tip, Legend, axisProps } from '../components/common.jsx'
import { int, gbp, pct, num } from '../format.js'

const MONTHS = 24
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const monthAfter = (asOf, i) => {
  const d = new Date(asOf)
  d.setMonth(d.getMonth() + i)
  return `${MON[d.getMonth()]} ${String(d.getFullYear()).slice(2)}`
}

function project({ backlog, inflow, capacity, target }) {
  const out = [backlog]
  let b = backlog
  let clear = null
  for (let i = 1; i <= MONTHS; i++) {
    b = Math.max(0, b + inflow - capacity)
    out.push(b)
    if (clear == null && b <= target) clear = i
  }
  return { series: out, clear }
}

export default function Planner() {
  const [d, setD] = useState(null)
  const [inflow, setInflow] = useState(0)
  const [fte, setFte] = useState(0)
  const [extra, setExtra] = useState(5)
  const [router, setRouter] = useState(true)
  const [target, setTarget] = useState(600)
  useEffect(() => { api.planner().then((r) => { setD(r); setInflow(r.inflow); setFte(r.assumed_fte) }) }, [])

  const calc = useMemo(() => {
    if (!d) return null
    const perAgent = d.closures / fte   // derived from recent closures ÷ the assumed headcount
    // Handling effort scales with the Finance cost model: transferred £121 vs £68.
    const s = d.transfer_share
    const s2 = s * (1 - d.router_defaults.adoption * d.router_defaults.avoidance)
    const effort = (x) => (1 - x) * d.cost.not + x * d.cost.transferred
    const speedup = effort(s) / effort(s2)
    const base = project({ backlog: d.backlog, inflow, capacity: (fte + extra) * perAgent, target })
    const withRouter = project({ backlog: d.backlog, inflow, capacity: (fte + extra) * perAgent * speedup, target })
    const today = project({ backlog: d.backlog, inflow, capacity: fte * perAgent, target })
    return { perAgent, speedup, base, withRouter, today }
  }, [d, inflow, fte, extra, target])

  if (!d || !calc) return <Loading />
  const chosen = router ? calc.withRouter : calc.base
  const data = calc.base.series.map((v, i) => ({
    i, label: i === 0 ? 'Now' : monthAfter(d.as_of, i), today: calc.today.series[i], plan: v, router: calc.withRouter.series[i],
  }))
  const clearLabel = chosen.clear != null ? monthAfter(d.as_of, chosen.clear) : 'not within 2 years'

  return (
    <div className="stack">
      <div className="grid g-7-5">
        <Card title="Inputs" sub="Headcount is an assumption we set and show: per-agent throughput = recent closures ÷ headcount">
          <div className="grid g2" style={{ gap: 18 }}>
            <label className="field">Inflow: <b className="tnum">{int(inflow)}</b> complaints / month
              <input type="range" min={800} max={1600} step={10} value={inflow} onChange={(e) => setInflow(+e.target.value)} />
              <span className="muted">default: last-3-month average ({int(d.inflow)})</span>
            </label>
            <label className="field">Assumed complaint-handling FTE: <b>{fte}</b>
              <input type="range" min={20} max={150} step={5} value={fte} onChange={(e) => setFte(+e.target.value)} />
              <span className="muted">→ {num(calc.perAgent)} closures per agent per month ({int(d.closures)} closed / month recently)</span>
            </label>
            <label className="field">Extra agents: <b>+{extra}</b> ({gbp(extra * d.fte_cost)} / yr at {gbp(d.fte_cost)} per FTE)
              <input type="range" min={0} max={30} step={1} value={extra} onChange={(e) => setExtra(+e.target.value)} />
            </label>
            <label className="field">"Cleared" means backlog below: <b>{int(target)}</b>
              <input type="range" min={0} max={1200} step={50} value={target} onChange={(e) => setTarget(+e.target.value)} />
              <span className="muted">≈ {num(target / inflow * 4.3, 1)} weeks of inflow in progress</span>
            </label>
          </div>
          <label className="row" style={{ marginTop: 14, cursor: 'pointer' }}>
            <input type="checkbox" checked={router} onChange={(e) => setRouter(e.target.checked)} />
            <span>Include the router: transfers fall from {pct(d.transfer_share)} to {pct(d.transfer_share * (1 - d.router_defaults.adoption * d.router_defaults.avoidance))} of closures,
              so each agent closes <b>{pct(calc.speedup - 1, 1)}</b> more (handling effort follows the £68 / £121 cost model)</span>
          </label>
        </Card>
        <Card title="Clearance">
          <div className="hero-num" style={{ fontSize: 40 }}>{clearLabel}</div>
          <div className="ink2" style={{ marginTop: 6 }}>
            {chosen.clear != null ? `Backlog falls below ${int(target)} in ${chosen.clear} month${chosen.clear > 1 ? 's' : ''}.` : 'The backlog keeps growing or plateaus above target.'}
          </div>
          <div className="stack small ink2" style={{ gap: 4, marginTop: 14 }}>
            <div>Today's capacity: {int(fte * calc.perAgent)} / month vs inflow {int(inflow)} → backlog {inflow > fte * calc.perAgent ? `grows ${int(inflow - fte * calc.perAgent)} a month` : 'shrinks'}</div>
            <div>This plan: {int((fte + extra) * calc.perAgent * (router ? calc.speedup : 1))} / month</div>
            <div>Extra agents cost {gbp(extra * d.fte_cost)} a year{router ? '; the router adds capacity worth ' + gbp(fte * (calc.speedup - 1) * d.fte_cost) + ' of headcount' : ''}</div>
          </div>
        </Card>
      </div>
      <Card title="Projected backlog" right={<Legend items={[
        { label: 'Today, no change', color: 'var(--axis)' },
        { label: `+${extra} agents`, color: 'var(--s2)' },
        { label: `+${extra} agents and router`, color: 'var(--s1)' },
      ]} />}>
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={data} margin={{ top: 10, right: 30, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--grid)" />
            <XAxis dataKey="label" {...axisProps} interval={2} />
            <YAxis {...axisProps} tickFormatter={int} />
            <ReferenceLine y={target} stroke="var(--good)" strokeDasharray="0" label={{ value: 'cleared', fill: 'var(--ink-2)', fontSize: 11, position: 'insideTopRight' }} />
            <Tooltip content={({ active, payload }) => active && payload?.length ? (
              <Tip head={payload[0].payload.label} rows={[
                { color: 'var(--axis)', label: 'Today', value: int(payload[0].payload.today) },
                { color: 'var(--s2)', label: `+${extra} agents`, value: int(payload[0].payload.plan) },
                { color: 'var(--s1)', label: '+ router', value: int(payload[0].payload.router) },
              ]} />) : null} />
            <Line dataKey="today" stroke="var(--axis)" strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line dataKey="plan" stroke="var(--s2)" strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line dataKey="router" stroke="var(--s1)" strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </Card>
    </div>
  )
}
