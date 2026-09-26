import React from 'react'
import { Card, Provenance } from './common.jsx'
import { pct, num, gbp } from '../format.js'

export default function TriageCard({ t, compact }) {
  const risk = t.legacy_route.transfer_risk
  const vs = [
    { k: 'Expected days to close', r: num(t.expected_days.routed), l: num(t.expected_days.legacy), d: t.expected_days.legacy - t.expected_days.routed, f: (v) => `${num(v)} days` },
    { k: 'SLA breach risk', r: pct(t.breach_risk.routed), l: pct(t.breach_risk.legacy), d: t.breach_risk.legacy - t.breach_risk.routed, f: (v) => `${(v * 100).toFixed(0)} pts` },
    { k: 'Reopen risk', r: pct(t.reopen_risk.routed), l: pct(t.reopen_risk.legacy), d: t.reopen_risk.legacy - t.reopen_risk.routed, f: (v) => `${(v * 100).toFixed(0)} pts` },
    { k: 'Handling cost', r: gbp(t.cost.routed), l: gbp(t.cost.legacy), d: t.cost.legacy - t.cost.routed, f: gbp },
  ]
  const maxShare = Math.max(...t.resolution_path.map((p) => p.share))
  return (
    <div className="stack" style={{ gap: 12 }}>
      <Card>
        <div className="row between"><span className="muted small">Route to</span><Provenance kind="policy" /></div>
        <div className="triage-owner">
          <span className="owner-team">{t.owner.team}</span>
          <span className="chip"><i className="dot" style={{ background: 'var(--s1)' }} />{t.owner.system}</span>
          {t.owner.linked_systems.map((s) => <span className="chip" key={s}>{s}</span>)}
        </div>
        <div className="small ink2" style={{ marginTop: 6 }}>
          Legacy route: entered via <b>{t.legacy_route.entry_system}</b>
          {risk > 0 ? <> , {pct(risk)} chance of a transfer</> : ' (no transfer risk)'}
        </div>
        {t.context.region_alert && (
          <div className="callout" style={{ marginTop: 10, borderColor: 'var(--critical)' }}>
            <span style={{ color: 'var(--critical)', fontWeight: 700 }}>⚠</span>
            <div><b>Regional alert.</b> {t.context.region_alert}</div>
          </div>
        )}
      </Card>

      <Card title="Legacy route vs non-transferred history" sub="What similar complaints did historically: an expectation, not a guarantee of what routing will achieve"
        right={<Provenance kind="observed" />}>
        <div className="vs">
          <span className="h" />
          <span className="h" style={{ textAlign: 'right' }}><i className="dot" style={{ background: 'var(--s2)', marginRight: 5 }} />Legacy</span>
          <span className="h" style={{ textAlign: 'right' }}><i className="dot" style={{ background: 'var(--s1)', marginRight: 5 }} />Not transferred</span>
          {vs.map((v) => (
            <React.Fragment key={v.k}>
              <span className="ink2">{v.k}</span>
              <span className="n" style={{ fontWeight: 400 }}>{v.l}</span>
              <span className="n">{v.r}</span>
            </React.Fragment>
          ))}
        </div>
        {risk > 0 && (
          <div className="small" style={{ marginTop: 10, color: 'var(--good-text)', fontWeight: 600 }}>
            If routing avoids the transfer: ~{vs[0].f(vs[0].d)}, {vs[1].f(vs[1].d)} of breach risk and ~{gbp(vs[3].d)} less on average, based on history
          </div>
        )}
      </Card>

      <div className={compact ? 'stack' : 'grid g2'} style={{ gap: 12 }}>
        <Card title="Likely resolution" sub="Share of similar non-transferred cases" right={<Provenance kind="observed" />}>
          <div className="path">
            <span className="h muted small">Action</span><span /><span className="muted small" style={{ textAlign: 'right' }}>Median</span><span className="muted small" style={{ textAlign: 'right' }}>Reopen</span>
            {t.resolution_path.map((p) => (
              <React.Fragment key={p.action}>
                <span>{p.action}</span>
                <span className="row" style={{ gap: 6, flexWrap: 'nowrap' }}>
                  <span className="bar" style={{ width: `${(p.share / maxShare) * 70}px` }} />
                  <span className="tnum small">{pct(p.share)}</span>
                </span>
                <span className="tnum" style={{ textAlign: 'right' }}>{p.median_days}d</span>
                <span className="tnum" style={{ textAlign: 'right' }}>{pct(p.reopen_rate)}</span>
              </React.Fragment>
            ))}
          </div>
          <div className="row" style={{ marginTop: 12 }}>
            <span className="chip" style={t.info_only_likelihood >= 0.45 ? { background: 'var(--accent-wash)', color: 'var(--ink)' } : {}}>
              Information-only likelihood <b className="tnum">{pct(t.info_only_likelihood)}</b>
            </span>
            {t.info_only_likelihood >= 0.45 && <span className="small ink2">auto-answer candidate</span>}
          </div>
        </Card>
        <Card title="Why" sub="Every number above, in words">
          <ul className="reasons">{t.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
          <div className="row" style={{ marginTop: 10 }}>
            {t.context.region_systems.map((s) => <span className="chip" key={s}>{s}</span>)}
            {t.context.region_signals?.estimated_read_rate != null && (
              <span className="chip">{pct(t.context.region_signals.estimated_read_rate)} est. reads · {pct(t.context.region_signals.smart_meter_penetration)} smart</span>
            )}
          </div>
        </Card>
      </div>
    </div>
  )
}
