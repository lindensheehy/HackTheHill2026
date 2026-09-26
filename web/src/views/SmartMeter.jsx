import React, { useMemo, useState } from 'react'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ScatterChart, Scatter, ReferenceLine,
} from 'recharts'
import { Card, Tip, Legend, Provenance, axisProps } from '../components/common.jsx'
import { pct, int, gbp, num } from '../format.js'

const FOCUS = ['Barrowdale', 'Dunmoor']

export default function SmartMeter({ s }) {
  const [excCost, setExcCost] = useState(34)
  const [years, setYears] = useState(4)
  const [coverage, setCoverage] = useState(s.target_coverage)

  const meters = Math.round(s.accounts_focus * coverage)
  const capex = meters * s.meter_cost
  // Hypothesis from the data: the benefit is fully there by ~30% coverage, so it scales with coverage up to 30%.
  const benefitShare = Math.min(1, coverage / 0.3)
  const annual = {
    complaints: s.complaints_avoided_per_year * s.complaint_cost * benefitShare,
    corrections: s.excess_bill_correction_per_year * benefitShare,
    exceptions: s.exceptions_avoided_per_year * excCost * benefitShare,
  }
  const annualTotal = annual.complaints + annual.corrections + annual.exceptions

  const data = useMemo(() => {
    const out = []
    let cost = 0
    let benefit = 0
    for (let y = 0; y <= 12; y++) {
      if (y > 0) {
        const installed = Math.min(1, y / years)
        const prevInstalled = Math.min(1, (y - 1) / years)
        cost += (installed - prevInstalled) * capex
        benefit += annualTotal * (installed + prevInstalled) / 2
      }
      out.push({ year: y, cost, benefit })
    }
    return out
  }, [capex, annualTotal, years])
  const payback = data.find((d) => d.year > 0 && d.benefit >= d.cost)

  const scatter = {
    focus: s.scatter.filter((p) => FOCUS.includes(p.region)),
    other: s.scatter.filter((p) => !FOCUS.includes(p.region)),
  }

  return (
    <Card title="#6 Smart meters: buy them in Barrowdale and Dunmoor"
      sub="Talking point with a projection. Everything except the unit costs is an estimate; the exception-handling cost is the number to ask Northwind for."
      right={<Provenance kind="assumption" />}>
      <div className="grid g-7-5">
        <div>
          <div className="grid g3" style={{ gap: 14, marginBottom: 12 }}>
            <label className="field">Exception handling cost: <b className="tnum">£{excCost}</b>
              <input type="range" min={0} max={34} step={1} value={excCost} onChange={(e) => setExcCost(+e.target.value)} />
              <span className="muted">£34 = Finance's manual-correction cost (upper bound); the real figure is the one to ask for</span>
            </label>
            <label className="field">Rollout: <b>{years} years</b>
              <input type="range" min={2} max={5} step={1} value={years} onChange={(e) => setYears(+e.target.value)} />
            </label>
            <label className="field">Coverage target: <b>{pct(coverage)}</b>
              <input type="range" min={0.1} max={1} step={0.05} value={coverage} onChange={(e) => setCoverage(+e.target.value)} />
              <span className="muted">{int(meters)} meters · {gbp(capex)}</span>
            </label>
          </div>
          <div className="row between">
            <h4>Cumulative cost vs benefit</h4>
            <Legend items={[{ label: 'Meter spend', color: 'var(--s2)' }, { label: 'Benefit', color: 'var(--s1)' }]} />
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={data} margin={{ top: 10, right: 30, bottom: 0, left: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--grid)" />
              <XAxis dataKey="year" {...axisProps} tickFormatter={(y) => `Y${y}`} />
              <YAxis {...axisProps} tickFormatter={gbp} width={56} />
              {payback && <ReferenceLine x={payback.year} stroke="var(--good)" label={{ value: `payback ~Y${payback.year}`, fill: 'var(--ink-2)', fontSize: 11, position: 'insideTopLeft' }} />}
              <Tooltip content={({ active, payload }) => active && payload?.length ? (
                <Tip head={`Year ${payload[0].payload.year}`} rows={[
                  { color: 'var(--s2)', label: 'Meter spend', value: gbp(payload[0].payload.cost) },
                  { color: 'var(--s1)', label: 'Benefit', value: gbp(payload[0].payload.benefit) },
                ]} />) : null} />
              <Line dataKey="cost" stroke="var(--s2)" strokeWidth={2} dot={false} isAnimationActive={false} />
              <Line dataKey="benefit" stroke="var(--s1)" strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
          <div className="grid g3" style={{ gap: 10, marginTop: 8 }}>
            <div><b>{gbp(annual.exceptions)}</b><div className="ink2 small">{int(s.exceptions_avoided_per_year * benefitShare)} exceptions avoided / yr</div></div>
            <div><b>{gbp(annual.corrections)}</b><div className="ink2 small">excess bill corrections / yr</div></div>
            <div><b>{gbp(annual.complaints)}</b><div className="ink2 small">{int(s.complaints_avoided_per_year * benefitShare)} billing complaints / yr</div></div>
          </div>
          <div className="muted small" style={{ marginTop: 8 }}>
            {payback ? `Pays back in about ${payback.year} years at £${excCost} per exception.` : 'No payback within 12 years at these settings.'}{' '}
            Not counted: field visits avoided (share of {int(s.meter_visits_2y)} × {gbp(s.field_visit_cost)}), regulator exposure, and less reliance on Aurora Billing's COBOL rating engine.
          </div>
        </div>
        <div>
          <div className="row between">
            <h4>Smart-meter coverage vs estimated reads</h4>
            <Legend items={[{ label: 'Barrowdale + Dunmoor', color: 'var(--s2)' }, { label: 'Other four', color: 'var(--s1)' }]} />
          </div>
          <ResponsiveContainer width="100%" height={250}>
            <ScatterChart margin={{ top: 10, right: 16, bottom: 10, left: -10 }}>
              <CartesianGrid stroke="var(--grid)" />
              <XAxis type="number" dataKey="pen" {...axisProps} domain={[0, 1]} tickFormatter={(v) => pct(v)}
                label={{ value: 'smart meter penetration', position: 'insideBottom', offset: -6, fill: 'var(--muted)', fontSize: 11 }} />
              <YAxis type="number" dataKey="est" {...axisProps} domain={[0, 0.8]} tickFormatter={(v) => pct(v)} />
              <Tooltip content={({ active, payload }) => active && payload?.length ? (
                <Tip head={`${payload[0].payload.region} · ${payload[0].payload.month}`} rows={[
                  { label: 'Smart meters', value: pct(payload[0].payload.pen) },
                  { label: 'Estimated reads', value: pct(payload[0].payload.est, 1) },
                ]} />) : null} />
              <Scatter data={scatter.focus} fill="var(--s2)" isAnimationActive={false} shape={dot('var(--s2)')} />
              <Scatter data={scatter.other} fill="var(--s1)" isAnimationActive={false} shape={dot('var(--s1)')} />
            </ScatterChart>
          </ResponsiveContainer>
          <div className="ink2 small">
            In the four smart regions, coverage went from 30% to 81% but estimated reads stayed around {pct(s.estimated_read.other)} (correlation {num(s.penetration_vs_estimated_corr, 2)}).
            <b> In this data the benefit shows up by ~30% coverage.</b> That's a hypothesis for Northwind to confirm, and the reason to redirect budget
            to the two regions at 0% ({pct(s.estimated_read.focus)} estimated, {num(s.exceptions_per_1k.focus)} vs {num(s.exceptions_per_1k.other)} exceptions per 1k).
          </div>
        </div>
      </div>
    </Card>
  )
}

const dot = (color) => (props) => (
  <circle cx={props.cx} cy={props.cy} r={4.5} fill={color} stroke="var(--surface)" strokeWidth={2} />
)
