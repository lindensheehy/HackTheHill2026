import React, { useEffect, useMemo, useState } from 'react'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, BarChart, Bar, ReferenceArea,
} from 'recharts'
import { api } from '../api.js'
import { Card, Loading, Sparkline, Tip, Legend, Provenance, axisProps } from '../components/common.jsx'
import { pct, int, num, gbp, fmt, monthLabel } from '../format.js'
import Alerts from './Alerts.jsx'
import SystemGraph from './SystemGraph.jsx'
import SmartMeter from './SmartMeter.jsx'

export default function Dashboard({ onAlertsChanged, alertArg }) {
  const [d, setD] = useState(null)
  const [replay, setReplay] = useState(null)
  const [graphKey, setGraphKey] = useState(0)
  useEffect(() => {
    api.dashboard().then(setD)
    api.replay().then(setReplay)
  }, [])
  if (!d) return <Loading />

  const alertsChanged = () => {
    onAlertsChanged()
    setGraphKey((k) => k + 1)
  }

  return (
    <div className="stack">
      <Hero k={d.kpis} />
      <KpiTiles tiles={d.kpis.tiles} />

      <SectionTitle step="How bad" title="Two years of degradation" />
      <div className="grid g-7-5">
        <SlaChart monthly={d.monthly} />
        <TransferPanel t={d.transfer} />
      </div>

      <SectionTitle step="Where" title="Regions" sub="Barrowdale and Dunmoor run on Aurora Billing and MeterHub, with no smart meters" />
      <RegionGrid regions={d.regions.regions} />

      <SectionTitle step="Why, and what's changing" title="Early warning" sub="Per-region signals vs each region's own trailing 6 months; alerts in 2+ regions are grouped with the systems they share" />
      <Alerts onChanged={alertsChanged} initial={alertArg} />
      <div className="grid g2">
        <Card title="System dependencies" sub="Regions → systems that serve them; entry systems → CaseTrack with today's transfer rate. Click a system.">
          <SystemGraph key={graphKey} />
        </Card>
        <Heatmap h={d.heatmap} />
      </div>

      <SectionTitle step="What's next" title="Where the money is" />
      <div className="grid g2">
        <RouterImpact replay={replay} transfer={d.transfer} />
        <InfoOnly tp={d.talking_points} />
      </div>
      <SmartMeter s={d.smart_meter} regions={d.regions} />
    </div>
  )
}

function SectionTitle({ step, title, sub }) {
  return (
    <div className="section-title" style={{ flexWrap: 'wrap' }}>
      <span className="step">{step}</span>
      <h2>{title}</h2>
      {sub && <span className="ink2 small">{sub}</span>}
    </div>
  )
}

function Hero({ k }) {
  const breach = k.tiles.find((t) => t.key === 'breach_rate')
  return (
    <Card>
      <div className="hero">
        <div>
          <div className="ink2">Regulator penalty exposure</div>
          <div className="hero-num">{gbp(k.penalty_per_quarter)}<span style={{ fontSize: 22 }}> / quarter</span></div>
        </div>
        <div className="hero-cap">
          SLA breaches rose from <b>{pct(k.first.breach_rate)}</b> to <b>{pct(breach.value)}</b> in two years.
          Time to close went from <b>{num(k.first.avg_days_to_close)}</b> to{' '}
          <b>{num(k.tiles[1].value)}</b> days, and the regulator score fell from <b>{num(k.first.regulator_score, 1)}</b> to{' '}
          <b>{num(k.tiles[4].value, 1)}</b>. The biggest fixable cause is complaints bouncing between systems.
        </div>
      </div>
    </Card>
  )
}

function KpiTiles({ tiles }) {
  return (
    <div className="grid g5">
      {tiles.map((t) => {
        const change = t.value - t.prior
        const worse = t.better === 'down' ? change > 0 : change < 0
        const rel = t.format === 'pct' ? `${change > 0 ? '+' : ''}${(change * 100).toFixed(1)} pts`
          : `${change > 0 ? '+' : ''}${t.format === 'int' ? int(change) : num(change, t.format === 'score' ? 2 : 1)}`
        return (
          <Card key={t.key} className="tile">
            <div className="label">{t.label}</div>
            <div className="value">{fmt(t.value, t.format)}</div>
            <div className={`delta ${worse ? 'bad' : 'good'}`}>
              {worse ? '▲' : '▼'} {rel} <span className="muted">vs {monthLabel(t.prior_month)}</span>
            </div>
            <Sparkline series={t.series} kind={t.format} />
            <div className="muted small">{monthLabel(t.month)}{t.key === 'breach_rate' ? ' cohort (latest complete)' : ''}</div>
          </Card>
        )
      })}
    </div>
  )
}

function SlaChart({ monthly }) {
  const data = monthly.map((m) => ({ ...m, label: monthLabel(m.month) }))
  const firstInc = data.find((m) => m.incomplete)
  const lastLabel = data[data.length - 1].label
  return (
    <Card title="SLA breach rate by month opened"
      sub="Closed complaints only; shaded months still have many cases open, so their rate will rise"
      right={<Legend items={[{ label: 'Monthly', color: 'var(--axis)' }, { label: '3-month rolling', color: 'var(--s1)' }]} />}>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 8, right: 36, bottom: 0, left: -12 }} syncId="sla">
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis dataKey="label" {...axisProps} interval={2} />
          <YAxis {...axisProps} domain={[0, 1]} tickFormatter={(v) => pct(v)} />
          {firstInc && <ReferenceArea x1={firstInc.label} x2={lastLabel} fill="var(--surface-2)" fillOpacity={1}
            label={{ value: 'still open', position: 'insideTop', fill: 'var(--muted)', fontSize: 11 }} />}
          <Tooltip cursor={{ stroke: 'var(--axis)' }} content={({ active, payload }) => active && payload?.length ? (
            <Tip head={payload[0].payload.label} rows={[
              { color: 'var(--axis)', label: 'Breach rate', value: pct(payload[0].payload.breach_rate, 1) },
              { color: 'var(--s1)', label: '3-month rolling', value: pct(payload[0].payload.breach_rate_3m, 1) },
              { label: 'Still open', value: pct(payload[0].payload.open_share) },
            ]} />) : null} />
          <Line dataKey="breach_rate" stroke="var(--axis)" strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line dataKey="breach_rate_3m" stroke="var(--s1)" strokeWidth={2} dot={false} isAnimationActive={false}
            label={({ x, y, index }) => index === data.length - 1 ? null : index === data.findLastIndex((m) => !m.incomplete)
              ? <text x={x + 6} y={y - 8} fontSize={11} fill="var(--ink)" fontWeight={600}>{pct(data[index].breach_rate_3m)}</text> : null} />
        </LineChart>
      </ResponsiveContainer>
      <div className="row between" style={{ marginTop: 10 }}>
        <h4>Opened vs closed per month</h4>
        <Legend square items={[{ label: 'Opened', color: 'var(--s2)' }, { label: 'Closed', color: 'var(--s1)' }]} />
      </div>
      <ResponsiveContainer width="100%" height={130}>
        <BarChart data={data} margin={{ top: 8, right: 36, bottom: 0, left: -12 }} barGap={2} syncId="sla">
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis dataKey="label" {...axisProps} interval={2} />
          <YAxis {...axisProps} />
          <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={({ active, payload }) => active && payload?.length ? (
            <Tip head={payload[0].payload.label} rows={[
              { color: 'var(--s2)', label: 'Opened', value: int(payload[0].payload.opened) },
              { color: 'var(--s1)', label: 'Closed', value: int(payload[0].payload.closed) },
            ]} foot={payload[0].payload.opened > payload[0].payload.closed ? 'Backlog grew' : 'Backlog shrank'} />) : null} />
          <Bar dataKey="opened" fill="var(--s2)" radius={[4, 4, 0, 0]} maxBarSize={10} isAnimationActive={false} />
          <Bar dataKey="closed" fill="var(--s1)" radius={[4, 4, 0, 0]} maxBarSize={10} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </Card>
  )
}

function TransferPanel({ t }) {
  const p = t.penalty
  const rows = [
    { label: 'Days to close', a: p.days.not, b: p.days.transferred, f: (v) => num(v) },
    { label: 'SLA breach', a: p.breach.not, b: p.breach.transferred, f: (v) => pct(v) },
    { label: 'Reopened', a: p.reopen.not, b: p.reopen.transferred, f: (v) => pct(v) },
    { label: 'Cost', a: p.cost.not, b: p.cost.transferred, f: (v) => gbp(v) },
  ]
  const spread = t.spread_outside_casetrack
  return (
    <Card title="The transfer penalty" sub={`${pct(p.transfer_share)} of closed complaints were transferred between systems`}
      right={<div className="stack" style={{ gap: 4, alignItems: 'flex-end' }}><Provenance kind="observed" /><Legend square items={[{ label: 'Not transferred', color: 'var(--s1)' }, { label: 'Transferred', color: 'var(--s2)' }]} /></div>}>
      <div className="cmp">
        {rows.map((r) => {
          const max = Math.max(r.a, r.b)
          return (
            <React.Fragment key={r.label}>
              <div className="cmp-label">{r.label}</div>
              <div className="cmp-bars">
                <div className="cmp-bar"><div className="fill" style={{ width: `${(r.a / max) * 70}%`, background: 'var(--s1)' }} /><b>{r.f(r.a)}</b></div>
                <div className="cmp-bar"><div className="fill" style={{ width: `${(r.b / max) * 70}%`, background: 'var(--s2)' }} /><b>{r.f(r.b)}</b>
                  <span className="mult">{(r.b / r.a).toFixed(1)}×</span></div>
              </div>
            </React.Fragment>
          )
        })}
      </div>
      <div style={{ height: 1, background: 'var(--grid)', margin: '16px 0' }} />
      <h4 style={{ marginBottom: 8 }}>Transfer rate by entry system</h4>
      <div className="cmp">
        {t.by_entry_system.map((s) => (
          <React.Fragment key={s.system}>
            <div className="cmp-label">{s.name}</div>
            <div className="cmp-bar"><div className="fill" style={{ width: `${s.rate * 140}%`, background: s.rate ? 'var(--s2)' : 'var(--s1)' }} /><b>{pct(s.rate)}</b></div>
          </React.Fragment>
        ))}
      </div>
      <div className="callout info" style={{ marginTop: 14 }}>
        <div>
          <b>It's where a complaint enters, not what it's about.</b> CaseTrack has no <i>recorded</i> transfers (that doesn't prove there are no handoffs). Elsewhere, transfer rates sit between{' '}
          {pct(Math.min(...Object.values(spread).map((s) => s.min)))} and {pct(Math.max(...Object.values(spread).map((s) => s.max)))}{' '}
          across every category, channel, priority and region. All {int(t.slowest_1pct.n)} of the slowest 1% (over {t.slowest_1pct.threshold_days} days) were transfers.
        </div>
      </div>
      <div className="row" style={{ marginTop: 12, gap: 16 }}>
        <span className="ink2 small">Last 12 months: <b className="tnum">{int(t.last_12m.transfers)}</b> transfers ≈ <b>{gbp(t.last_12m.gbp)}</b> extra handling,{' '}
          <b>{int(t.last_12m.days)}</b> complaint-days, <b>{int(t.last_12m.reopens)}</b> reopens</span>
      </div>
    </Card>
  )
}

function RegionGrid({ regions }) {
  const max = (k) => Math.max(...regions.map((r) => r[k]))
  return (
    <div className="grid g3">
      {regions.map((r) => (
        <Card key={r.region} className={`region ${r.focus ? 'focus' : ''}`}>
          <div className="row between">
            <h3>{r.region}</h3>
            <span className="muted small tnum">{int(r.accounts)} accounts</span>
          </div>
          <div className="row" style={{ marginTop: 6 }}>
            {r.systems.map((s) => <span className="chip" key={s.id}>{s.id} {s.name}</span>)}
          </div>
          <div className="metrics">
            <Metric k="SLA breach (12m)" v={pct(r.breach_rate)} />
            <Metric k="Complaints / 1k acc." v={num(r.complaints_per_1k)} bar={r.complaints_per_1k / max('complaints_per_1k')} />
            <Metric k="Estimated reads" v={pct(r.estimated_read_rate)} bar={r.estimated_read_rate} />
            <Metric k="Smart meters" v={pct(r.smart_meter_penetration)} bar={r.smart_meter_penetration}
              note={r.smart_meter_start !== r.smart_meter_penetration ? `from ${pct(r.smart_meter_start)}` : 'never rolled out'} />
            <Metric k="Billing exceptions / 1k / mo" v={num(r.exceptions_per_1k)} bar={r.exceptions_per_1k / max('exceptions_per_1k')} />
            <Metric k="Bill-correction value" v={pct(r.bill_correction_share)} note="share of total" />
          </div>
          <div className="row" style={{ marginTop: 12 }}>
            <a className="btn sm" href={`#/queue?region=${encodeURIComponent(r.region)}`}>Open complaints ({int(r.open_now)}) →</a>
            <a className="btn sm" href={`#/queue?region=${encodeURIComponent(r.region)}&priority=P1`}>P1 only</a>
          </div>
        </Card>
      ))}
    </div>
  )
}

function Metric({ k, v, bar, note }) {
  return (
    <div className="metric">
      <div className="k">{k}</div>
      <div className="v">{v} {note && <span className="muted small" style={{ fontWeight: 400 }}>{note}</span>}</div>
      {bar != null && <div className="meter"><div style={{ width: `${Math.min(1, bar) * 100}%` }} /></div>}
    </div>
  )
}

function Heatmap({ h }) {
  const [hover, setHover] = useState(null)
  const step = (idx) => {
    // sequential blue ramp over the index vs the category's own mean
    const t = Math.max(0, Math.min(1, (idx - 0.5) / 1.2))
    const steps = ['var(--seq-100)', 'var(--seq-250)', 'var(--seq-400)', 'var(--seq-550)', 'var(--seq-700)']
    return steps[Math.min(steps.length - 1, Math.floor(t * steps.length))]
  }
  return (
    <Card title="Category × month" sub="Complaints opened, shaded against each category's own 2-year average"
      right={hover ? <span className="small tnum"><b>{hover.cat}</b> · {monthLabel(hover.m)} · {int(hover.n)} ({num(hover.i, 2)}× avg)</span>
        : <span className="muted small">hover a cell</span>}>
      <div className="heat" style={{ gridTemplateColumns: `170px repeat(${h.months.length}, minmax(0, 1fr))` }}
        onMouseLeave={() => setHover(null)}>
        {h.rows.map((r) => (
          <React.Fragment key={r.category}>
            <div className="rl" title={r.category}>{r.category}</div>
            {r.counts.map((n, i) => (
              <div key={i} className="cell" style={{ background: step(r.index[i]), outline: hover?.cat === r.category && hover?.m === h.months[i] ? '2px solid var(--ink)' : 'none' }}
                onMouseEnter={() => setHover({ cat: r.category, m: h.months[i], n, i: r.index[i] })} />
            ))}
          </React.Fragment>
        ))}
        <div />
        {h.months.map((m, i) => <div key={m} className="muted" style={{ textAlign: 'center', fontSize: 10 }}>{i % 3 === 0 ? monthLabel(m) : ''}</div>)}
      </div>
      <div className="row small muted" style={{ marginTop: 10, gap: 6 }}>
        <span>Below average</span>
        {['--seq-100', '--seq-250', '--seq-400', '--seq-550', '--seq-700'].map((v) => <i key={v} className="dot" style={{ width: 18, borderRadius: 3, background: `var(${v})` }} />)}
        <span>Above average</span>
        <span style={{ marginLeft: 'auto' }}>No category peaks above ~1.5× its average: volume grows everywhere at once</span>
      </div>
    </Card>
  )
}

function RouterImpact({ replay, transfer }) {
  const [adoption, avoidance] = [0.8, 0.6]
  if (!replay) return <Card title="Router impact"><Loading /></Card>
  const n = replay.annual_transfers * adoption * avoidance
  const per = replay.per_avoided
  return (
    <Card title="#1 Route at intake" sub={`Scenario: annualised at ${pct(adoption)} adoption and ${pct(avoidance)} of would-be transfers avoided. Not a measured effect.`}
      right={<div className="stack" style={{ gap: 4, alignItems: 'flex-end' }}><Provenance kind="assumption" /><a href="#/replay" className="small">Run the replay →</a></div>}>
      <div className="grid g2" style={{ gap: 12 }}>
        <Stat v={int(n)} k="transfers avoided / yr" />
        <Stat v={gbp(n * per.gbp)} k="handling cost saved" />
        <Stat v={int(n * per.days)} k="complaint-days saved" />
        <Stat v={int(n * per.reopens)} k="reopens avoided" />
      </div>
      <div className="muted small" style={{ marginTop: 10 }}>
        Upper bound at 100% / 100%: {gbp(transfer.last_12m.gbp)}, {int(transfer.last_12m.days)} days, {int(transfer.last_12m.reopens)} reopens, {int(transfer.last_12m.breaches)} breaches.
        Unit costs: Finance cost model FY26.
      </div>
    </Card>
  )
}

function Stat({ v, k }) {
  return (
    <div>
      <div style={{ fontSize: 26, fontWeight: 600, letterSpacing: '-0.02em' }}>{v}</div>
      <div className="ink2 small">{k}</div>
    </div>
  )
}

function InfoOnly({ tp }) {
  const io = tp.info_only
  const pilot = tp.ai_pilot
  const first = pilot[0]
  const last = pilot[pilot.length - 1]
  const cats = Object.entries(io.by_category)
  return (
    <Card title="#4 Auto-answer information-only complaints" sub="Talking point, with a stub lane in the triage queue"
      right={<div className="stack" style={{ gap: 4, alignItems: 'flex-end' }}><Provenance kind="observed" /><a href="#/queue/auto" className="small">See the lane →</a></div>}>
      <div className="grid g2" style={{ gap: 12 }}>
        <Stat v={pct(io.share)} k={`needed information only (~${int(io.per_year)} a year)`} />
        <Stat v={gbp(io.half_saving)} k="a year if half are auto-answered" />
      </div>
      <div style={{ marginTop: 12 }} className="cmp">
        {cats.slice(0, 4).map(([c, v]) => (
          <React.Fragment key={c}>
            <div className="cmp-label" title={c} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.replace('Service - ', '').replace(' - ', ': ')}</div>
            <div className="cmp-bar"><div className="fill" style={{ width: `${v * 100}%`, background: 'var(--s1)' }} /><b>{pct(v)}</b></div>
          </React.Fragment>
        ))}
      </div>
      <div className="ink2 small" style={{ marginTop: 10 }}>
        They reopen no more often than other complaints ({pct(io.reopen.info_only, 1)} vs {pct(io.reopen.other, 1)}), so answering with information works.
        Not another chatbot: the {gbp(tp.ai_pilot_cost)}/yr AI pilot fell from {pct(first.fully_contained_rate)} to {pct(last.fully_contained_rate)} fully resolved,
        with repeat contact up from {pct(first.repeat_contact_within_7_days_rate)} to {pct(last.repeat_contact_within_7_days_rate)}.
      </div>
    </Card>
  )
}
