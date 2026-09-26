import React, { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { Card, Loading, Pri, Overdue, Provenance } from '../components/common.jsx'
import TriageCard from '../components/TriageCard.jsx'
import CustomerUpdate from '../components/CustomerUpdate.jsx'
import Planner from './Planner.jsx'
import { useSession } from '../session.js'
import { pct, int, num } from '../format.js'

const PAGE = 100
const FILTER_KEYS = ['region', 'category', 'priority', 'owner', 'system', 'search']

export default function Queue({ meta, highlight, params }) {
  const sub = highlight === 'auto' ? 'auto' : highlight === 'planner' ? 'planner' : 'queue'
  const setSub = (s) => { window.location.hash = s === 'queue' ? '/queue' : `/queue/${s}` }
  return (
    <div className="stack" style={{ gap: 0 }}>
      <div className="row between" style={{ marginBottom: 12 }}>
        <div>
          <h2>Triage queue</h2>
          <div className="ink2">Every open complaint, ranked. Timing is computed from dates as of the data's last day, not from the stored breach flag.</div>
        </div>
      </div>
      <div className="subtabs" role="tablist">
        {[['queue', 'Queue'], ['auto', 'Auto-answer lane'], ['planner', 'Backlog planner']].map(([k, label]) => (
          <button key={k} role="tab" aria-selected={sub === k} className={`subtab ${sub === k ? 'active' : ''}`} onClick={() => setSub(k)}>{label}</button>
        ))}
      </div>
      {sub === 'queue' && <QueueTable meta={meta} highlight={highlight} params={params} />}
      {sub === 'auto' && <AutoLane />}
      {sub === 'planner' && <Planner />}
    </div>
  )
}

function QueueTable({ meta, highlight, params = {} }) {
  const initial = Object.fromEntries(FILTER_KEYS.map((k) => [k, params[k] || '']))
  const [filters, setFilters] = useState(initial)
  const [strict, setStrict] = useState(false)
  const [data, setData] = useState(null)
  const [page, setPage] = useState(0)
  const [cursor, setCursor] = useState(0)
  const [open, setOpen] = useState(highlight && highlight.startsWith('NW-') ? highlight : null)
  const [version, setVersion] = useState(0)
  const [help, setHelp] = useState(false)
  const rowRefs = useRef({})
  const searchRef = useRef()

  useEffect(() => { setFilters(Object.fromEntries(FILTER_KEYS.map((k) => [k, params[k] || '']))) }, [JSON.stringify(params)])
  useEffect(() => {
    api.queue({ ...filters, strict, limit: 2000 }).then((d) => {
      setData(d)
      const idx = highlight ? d.rows.findIndex((r) => r.complaint_id === highlight) : -1
      setPage(idx >= 0 ? Math.floor(idx / PAGE) : 0)
      setCursor(idx >= 0 ? idx % PAGE : 0)
    })
  }, [filters, strict, version])

  const rows = data ? data.rows.slice(page * PAGE, (page + 1) * PAGE) : []
  useEffect(() => {
    const id = rows[cursor]?.complaint_id
    rowRefs.current[id]?.scrollIntoView({ block: 'nearest' })
  }, [cursor, page, data])
  useEffect(() => {
    if (highlight && rowRefs.current[highlight]) rowRefs.current[highlight].scrollIntoView({ block: 'center' })
  }, [data])

  // Keyboard: / search, j/k or arrows move, Enter opens, ? help. Ignored while typing or with the drawer open.
  useEffect(() => {
    const onKey = (e) => {
      const typing = ['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName)
      if (open || typing || e.metaKey || e.ctrlKey || e.altKey) return
      if (e.key === '/') { e.preventDefault(); searchRef.current?.focus() }
      else if (e.key === 'j' || e.key === 'ArrowDown') { e.preventDefault(); setCursor((c) => Math.min(rows.length - 1, c + 1)) }
      else if (e.key === 'k' || e.key === 'ArrowUp') { e.preventDefault(); setCursor((c) => Math.max(0, c - 1)) }
      else if (e.key === 'Enter' && rows[cursor]) { e.preventDefault(); setOpen(rows[cursor].complaint_id) }
      else if (e.key === '?') setHelp((h) => !h)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, rows, cursor])

  if (!meta || !data) return <Loading />
  const s = data.summary
  const pages = Math.ceil(data.rows.length / PAGE)
  const set = (k) => (e) => setFilters({ ...filters, [k]: e.target.value })
  const active = FILTER_KEYS.filter((k) => filters[k])

  return (
    <div className="stack">
      <div className="grid g5">
        <Card className="tile"><div className="label">In queue</div><div className="value">{int(s.total)}</div>
          <div className="muted small">{s.by_priority.P1 || 0} P1 · {s.by_priority.P2 || 0} P2 · {s.by_priority.P3 || 0} P3</div></Card>
        <Card className="tile"><div className="label">Past SLA (from dates)</div><div className="value">{int(s.breached)}</div>
          <div className="muted small">{s.total ? pct(s.breached / s.total) : '–'} of the queue</div></Card>
        <Card className="tile"><div className="label">Due within 2 days</div><div className="value">{int(s.amber)}</div></Card>
        <Card className="tile"><div className="label">Median overdue</div><div className="value">{num(s.median_overdue_days, 0)} days</div>
          <div className="muted small">worst: {s.max_overdue_days} days over</div></Card>
        <Card className="tile"><div className="label">Stored flag says breached</div><div className="value">{pct(s.stored_flag_breached_share)}</div>
          <div className="muted small">why we compute from dates</div></Card>
      </div>

      <Card>
        <div className="row" style={{ gap: 10 }}>
          <input ref={searchRef} type="search" placeholder="Search account or complaint ID  ( / )" value={filters.search} onChange={set('search')} style={{ minWidth: 240 }} aria-label="Search" />
          <select value={filters.priority} onChange={set('priority')} aria-label="Priority"><option value="">All priorities</option>{meta.priorities.map((p) => <option key={p}>{p}</option>)}</select>
          <select value={filters.region} onChange={set('region')} aria-label="Region"><option value="">All regions</option>{meta.regions.map((p) => <option key={p}>{p}</option>)}</select>
          <select value={filters.category} onChange={set('category')} aria-label="Category"><option value="">All categories</option>{meta.categories.map((p) => <option key={p}>{p}</option>)}</select>
          <select value={filters.owner} onChange={set('owner')} aria-label="Owner"><option value="">All owners</option>{meta.teams.map((p) => <option key={p}>{p}</option>)}</select>
          <select value={filters.system} onChange={set('system')} aria-label="Entry system"><option value="">All entry systems</option>{meta.entry_systems.map((p) => <option key={p.id} value={p.id}>{p.id} {p.name}</option>)}</select>
          {active.length > 0 && <button className="btn sm" onClick={() => setFilters(Object.fromEntries(FILTER_KEYS.map((k) => [k, ''])))}>Clear filters</button>}
          <span style={{ flex: 1 }} />
          <label className="row small" style={{ gap: 6, cursor: 'pointer' }} title="Sort by priority, then days overdue">
            <input type="checkbox" checked={strict} onChange={(e) => setStrict(e.target.checked)} /> Strict mode (priority, then overdue)
          </label>
          <button className="btn sm" onClick={() => setHelp(!help)} aria-expanded={help}>Keys ?</button>
        </div>
        {help && (
          <div className="small ink2" style={{ marginTop: 10 }}>
            <kbd>/</kbd> search · <kbd>j</kbd>/<kbd>k</kbd> or <kbd>↑</kbd>/<kbd>↓</kbd> move · <kbd>Enter</kbd> open case · <kbd>Esc</kbd> close · <kbd>?</kbd> toggle this help
          </div>
        )}
      </Card>

      <div className="table-wrap" style={{ maxHeight: '64vh' }}>
        <table aria-label="Ranked open complaints">
          <thead>
            <tr>
              <th className="num">#</th><th>ID</th><th>Pri</th><th>Category</th><th>Region</th><th className="num">Age</th>
              <th>SLA</th><th>Owner</th><th>Flags</th><th className="num">Score</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.complaint_id} ref={(el) => { rowRefs.current[r.complaint_id] = el }}
                className={`click ${r.complaint_id === highlight ? 'new' : ''} ${r.complaint_id === open ? 'sel' : ''} ${i === cursor ? 'cursor' : ''}`}
                onClick={() => { setCursor(i); setOpen(r.complaint_id) }} aria-selected={i === cursor}>
                <td className="num muted">{r.rank}</td>
                <td className="tnum">{r.complaint_id}</td>
                <td><Pri p={r.priority} /></td>
                <td>{r.category}</td>
                <td>{r.region}</td>
                <td className="num">{r.age_days}d</td>
                <td><Overdue days={r.overdue_days} state={r.overdue_state} /></td>
                <td className="ink2">{r.owner_team}</td>
                <td>
                  <span className="row" style={{ gap: 4, flexWrap: 'nowrap' }}>
                    {r.from_intake && <span className="chip" style={{ background: 'var(--accent-wash)', color: 'var(--ink)' }}>routed</span>}
                    {r.transferred_between_systems ? <span className="chip" title="Transferred between systems">transferred</span> : null}
                    {r.alert_id && <span className="chip alert-chip" title={r.alert_summary}>⚠ alert</span>}
                    {r.workflow_status !== 'new' && <span className="chip">{r.workflow_status.replace('_', ' ')}</span>}
                    {r.bounced_from_auto && <span className="chip">back from auto</span>}
                  </span>
                </td>
                <td className="num" title={r.why.join('\n')}><b>{num(r.queue_score, 2)}</b></td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <div className="empty">No open complaints match.</div>}
      </div>
      <div className="row between">
        <span className="muted small">
          <Provenance kind="policy" />{' '}
          {strict ? 'Strict mode: priority first, then days overdue.'
            : `Score = priority weight × (1 + overdue ratio) once past SLA; before that, weight × breach risk × imminence. +${data.config.transferred_bonus} transferred, +${data.config.alert_bonus} live alert.`}
        </span>
        {pages > 1 && (
          <span className="row">
            <button className="btn sm" disabled={page === 0} onClick={() => { setPage(page - 1); setCursor(0) }}>← Prev</button>
            <span className="small tnum">{page * PAGE + 1}–{Math.min(data.rows.length, (page + 1) * PAGE)} of {int(data.rows.length)}</span>
            <button className="btn sm" disabled={page >= pages - 1} onClick={() => { setPage(page + 1); setCursor(0) }}>Next →</button>
          </span>
        )}
      </div>
      {open && <CaseDrawer id={open} meta={meta} onClose={() => setOpen(null)} onChanged={() => setVersion((v) => v + 1)} />}
    </div>
  )
}

function CaseDrawer({ id, meta, onClose, onChanged }) {
  const { can, setFocus } = useSession()
  const [d, setD] = useState(null)
  const [note, setNote] = useState('')
  const [err, setErr] = useState(null)
  const [version, setVersion] = useState(0)
  const closeRef = useRef()
  useEffect(() => { setD(null); api.caseDetail(id).then(setD); setFocus({ case_id: id }); return () => setFocus({}) }, [id])
  useEffect(() => { closeRef.current?.focus() }, [d === null])
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && !document.querySelector('.assistant') && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const act = async (ev) => {
    setErr(null)
    try {
      setD(await api.event(id, ev))
      setVersion((v) => v + 1)
      onChanged()
    } catch (e) {
      setErr(e.message)
    }
  }
  const lock = (perm) => (can(perm) ? {} : { disabled: true, title: `Your role can't do this (needs ${perm})` })

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label={`Case ${id}`}>
        {!d ? <Loading /> : (
          <>
            <div className="row between">
              <div className="row">
                <h2>{id}</h2>
                {d.case.priority && <Pri p={d.case.priority} />}
                {d.case.overdue_state && <Overdue days={d.case.overdue_days} state={d.case.overdue_state} />}
              </div>
              <button ref={closeRef} className="btn sm" onClick={onClose}>Close (Esc)</button>
            </div>
            {d.case.closed ? <div className="callout">This complaint is {d.case.status.toLowerCase()}.</div> : (
              <>
                <Card className="four">
                  <Q label="What happened" kind="observed">{d.summary.what_happened}</Q>
                  <Q label="What happens next" kind="policy">{d.summary.next_action}</Q>
                  <Q label="Who owns it" kind="policy">{d.summary.owner}</Q>
                  <Q label="What's blocking it" kind="policy">
                    <ul className="reasons">{d.summary.blockers.map((b, i) => <li key={i}>{b}</li>)}</ul>
                  </Q>
                </Card>
                {d.case.workflow_status !== 'resolved' && (
                  <Card title={d.case.rank ? `Why is this case #${d.case.rank} in the full queue?` : 'Why this score?'} sub={`Queue score ${num(d.case.queue_score, 2)}`}
                    right={<Provenance kind="policy" />}>
                    <ul className="reasons">{d.case.why.map((w, i) => <li key={i}>{w}</li>)}</ul>
                    {d.case.in_auto_lane && <div className="callout info" style={{ marginTop: 10 }}><div>In the auto-answer lane: <b>{d.case.auto_template}</b> sent, watching for 7 days.</div></div>}
                  </Card>
                )}
                <Card title="Actions">
                  <div className="stack" style={{ gap: 10 }}>
                    <div className="row">
                      <label className="small ink2" htmlFor="owner-select">Owner</label>
                      <select id="owner-select" value={d.case.owner_team} onChange={(e) => act({ type: 'assign', value: e.target.value })} {...lock('cases:assign')}>
                        {meta.teams.map((t) => <option key={t}>{t}</option>)}
                      </select>
                      <span className="small ink2" style={{ marginLeft: 8 }}>Status: <b>{d.case.workflow_status.replace('_', ' ')}</b></span>
                    </div>
                    <div className="row">
                      <button className="btn sm" onClick={() => act({ type: 'status', value: 'in_progress' })} {...lock('cases:write')}>In progress</button>
                      <button className="btn sm warn" onClick={() => act({ type: 'status', value: 'escalated' })} {...lock('cases:write')}>Escalate</button>
                      <button className="btn sm primary" onClick={() => act({ type: 'status', value: 'resolved' }).then(onClose)} {...lock('cases:write')}>Resolve</button>
                    </div>
                    <div className="row" style={{ flexWrap: 'nowrap' }}>
                      <input type="text" placeholder="Add a note" value={note} onChange={(e) => setNote(e.target.value)} style={{ flex: 1 }} aria-label="Note" {...lock('cases:write')} />
                      <button className="btn sm" disabled={!note || !can('cases:write')} onClick={() => { act({ type: 'note', note }); setNote('') }}>Add</button>
                    </div>
                    {err && <div className="small" style={{ color: 'var(--critical)' }}>{err}</div>}
                    {d.events.length > 0 && (
                      <div className="small ink2">
                        {d.events.slice().reverse().map((e) => (
                          <div key={e.event_id}>{e.ts.replace('T', ' ')} · <b>{e.type.replace('_', ' ')}</b> {e.value || ''} {e.note || ''}</div>
                        ))}
                      </div>
                    )}
                  </div>
                </Card>
                <CustomerUpdate id={id} version={version} onHelp={() => act({ type: 'customer_help', note: 'Customer pressed “I still need help”' })} />
              </>
            )}
            {d.alert && (
              <div className="callout" style={{ borderColor: 'var(--critical)' }}>
                <span style={{ color: 'var(--critical)', fontWeight: 700 }} aria-hidden>⚠</span>
                <div><b>Linked regional alert</b> {d.alert.synthetic ? <Provenance kind="simulated" /> : null}
                  <div>{d.alert.detail.summary}</div>
                  <a href={`#/dashboard/${d.alert.alert_id}`} className="small">Open investigation →</a>
                </div>
              </div>
            )}
            <Card title="Account history" sub={d.history.length ? `${d.history.length} other complaint${d.history.length > 1 ? 's' : ''} on ${d.case.account_id}` : 'No other complaints on this account'}>
              {d.history.length > 0 && (
                <div className="timeline">
                  {d.history.map((h) => (
                    <div className="tl-item" key={h.complaint_id}>
                      <div><b className="tnum">{h.date_opened}</b> · {h.complaint_id} · {h.category} <Pri p={h.priority} /></div>
                      <div className="small ink2">
                        {h.status}{h.days_to_close != null ? ` in ${h.days_to_close} days` : ''}{h.resolution_action ? ` · ${h.resolution_action}` : ''}
                        {h.transferred ? ' · transferred' : ''}{h.reopened ? ' · reopened' : ''}
                      </div>
                    </div>
                  ))}
                  <div className="tl-item cur"><b>Now</b> · {id}</div>
                </div>
              )}
            </Card>
            <TriageCard t={d.triage} compact />
          </>
        )}
      </aside>
    </>
  )
}

function Q({ label, kind, children }) {
  return (
    <div className="q">
      <div className="row between"><span className="q-label">{label}</span><Provenance kind={kind} /></div>
      <div className="q-body">{children}</div>
    </div>
  )
}

function AutoLane() {
  const { can } = useSession()
  const [d, setD] = useState(null)
  const load = () => api.autoLane().then(setD)
  useEffect(() => { load() }, [])
  if (!d) return <Loading />
  const bounce = async (id) => {
    await api.event(id, { type: 'auto_bounce', note: 'Customer came back after the automatic answer' })
    load()
  }
  return (
    <div className="stack">
      <div className="callout info">
        <div>
          <Provenance kind="policy" /> <b>Stub for talking point #4.</b> Fresh complaints (≤ 14 days old) with ≥ {pct(d.threshold)} information-only likelihood and an answer template are
          answered automatically and watched for {d.watch_days} days. If the customer comes back, the case moves to the priority queue with everything attached.
        </div>
      </div>
      <div className="table-wrap" style={{ maxHeight: '60vh' }}>
        <table>
          <thead><tr><th>ID</th><th>Pri</th><th>Category</th><th>Region</th><th>Opened</th><th className="num">Info-only</th><th>Answer sent</th><th>Watch until</th><th /></tr></thead>
          <tbody>
            {d.rows.map((r) => (
              <tr key={r.complaint_id}>
                <td className="tnum">{r.complaint_id}{r.from_intake && <span className="chip" style={{ marginLeft: 6 }}>routed</span>}</td>
                <td><Pri p={r.priority} /></td><td>{r.category}</td><td>{r.region}</td>
                <td className="tnum">{r.date_opened}</td><td className="num">{pct(r.info_only_likelihood)}</td>
                <td className="ink2">{r.auto_template}</td><td className="tnum">{r.watch_until}</td>
                <td><button className="btn sm" onClick={() => bounce(r.complaint_id)} disabled={!can('cases:write')}>Customer came back</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        {d.rows.length === 0 && <div className="empty">Nothing in the lane.</div>}
      </div>
      {d.bounced.length > 0 && (
        <Card title="Moved to the queue" sub="Customer came back after the automatic answer">
          <table><tbody>
            {d.bounced.map((r) => (
              <tr key={r.complaint_id} className="click" onClick={() => { window.location.hash = `/queue/${r.complaint_id}` }}>
                <td className="tnum">{r.complaint_id}</td><td><Pri p={r.priority} /></td><td>{r.category}</td><td>{r.region}</td>
                <td><Overdue days={r.overdue_days} state={r.overdue_state} /></td><td className="ink2">see it in the queue →</td>
              </tr>
            ))}
          </tbody></table>
        </Card>
      )}
    </div>
  )
}
