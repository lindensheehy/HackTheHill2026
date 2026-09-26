import React from 'react'
import { fmt, monthLabel } from '../format.js'

export function Card({ title, sub, right, children, className = '', style }) {
  return (
    <section className={`card ${className}`} style={style}>
      {(title || right) && (
        <div className="card-head">
          <div>
            {title && <h3>{title}</h3>}
            {sub && <div className="card-sub">{sub}</div>}
          </div>
          {right}
        </div>
      )}
      {children}
    </section>
  )
}

export function Loading({ label = 'Loading…' }) {
  return <div className="spinner">{label}</div>
}

export function Pri({ p }) {
  return <span className={`pri ${p}`}>{p}</span>
}

export function Overdue({ days, state }) {
  const text = days > 0 ? `${days}d over` : days === 0 ? 'due today' : `${-days}d left`
  const label = state === 'red' ? 'Past SLA' : state === 'amber' ? 'Due within 2 days' : 'Inside SLA'
  return (
    <span className={`od ${state}`} title={label}>
      <i className={`dot ${state}`} />
      {text}
    </span>
  )
}

/** Tooltip body used by every Recharts chart. rows: [{color, label, value}] */
export function Tip({ head, rows, foot }) {
  return (
    <div className="tooltip">
      {head && <div className="t-head">{head}</div>}
      {rows.map((r, i) => (
        <div className="t-row" key={i}>
          <span className="row" style={{ gap: 6 }}>
            {r.color && <i className="dot" style={{ background: r.color }} />}
            {r.label}
          </span>
          <b>{r.value}</b>
        </div>
      ))}
      {foot && <div className="muted small" style={{ marginTop: 4 }}>{foot}</div>}
    </div>
  )
}

export function Sparkline({ series, kind, height = 32 }) {
  const vals = series.map((s) => s.v).filter((v) => v != null)
  if (!vals.length) return null
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const w = 160
  const pad = 4
  const x = (i) => pad + (i / (series.length - 1)) * (w - 2 * pad)
  const y = (v) => height - pad - ((v - min) / (max - min || 1)) * (height - 2 * pad)
  const d = series.map((s, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(s.v).toFixed(1)}`).join('')
  const last = series[series.length - 1]
  return (
    <svg viewBox={`0 0 ${w} ${height}`} width="100%" height={height} preserveAspectRatio="none" aria-hidden>
      <path d={d} fill="none" stroke="var(--axis)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      <circle cx={x(series.length - 1)} cy={y(last.v)} r="3.5" fill="var(--s1)" stroke="var(--surface)" strokeWidth="2" />
      <title>{`${monthLabel(series[0].month)}: ${fmt(series[0].v, kind)} → ${monthLabel(last.month)}: ${fmt(last.v, kind)}`}</title>
    </svg>
  )
}

export function Legend({ items, square }) {
  return (
    <div className="legend">
      {items.map((it) => (
        <span key={it.label}>
          <i className={square ? 'sq' : ''} style={{ background: it.color }} />
          {it.label}
        </span>
      ))}
    </div>
  )
}

export const axisProps = {
  tick: { fill: 'var(--muted)', fontSize: 11 },
  axisLine: { stroke: 'var(--axis)' },
  tickLine: false,
}
