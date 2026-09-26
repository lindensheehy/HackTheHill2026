"""Queue service: open complaints + intake complaints, with case_events applied, ranked."""

import json
from datetime import datetime

import pandas as pd

from engine import build_baselines, context, db, queue_score, router

# Talking point #4 (stub): answer templates we could send without an agent.
AUTO_TEMPLATES = {
    "Other": "General enquiry answer pack",
    "Service - poor communication": "Case status update with a named contact",
    "Water - pressure or quality": "Live network status from AquaTrack",
    "Supply - interruption": "Outage status and restoration time from GridWatch",
    "Billing - estimated read": "Estimated-read explanation with a submit-a-read link",
}
AUTO_THRESHOLD = 0.45     # info-only likelihood needed to auto-answer
AUTO_MAX_AGE = 14         # only fresh complaints are candidates
AUTO_WATCH_DAYS = 7

EVENT_TYPES = {"assign", "status", "note", "auto_bounce", "customer_help"}
STATUSES = {"in_progress", "resolved", "escalated"}


def _events():
    return db.store().df("SELECT * FROM case_events ORDER BY event_id")


def _latest(ev, typ):
    e = ev[ev["type"] == typ]
    return e.groupby("complaint_id")["value"].last().to_dict() if not e.empty else {}


def info_only_rates(df):
    io = build_baselines.load()["info_only"]
    return [
        (io.get(f"{c}|{ch}") or io.get(f"{c}|*") or {"rate": 0.0})["rate"]
        for c, ch in zip(df["category"], df["channel"])
    ]


def open_cases(include_auto=False):
    """All open cases with scores and workflow state. Resolved cases are dropped."""
    df = context.all_complaints()
    df = df[df["is_open"]].copy()
    ev = _events()
    status, owner, bounced = _latest(ev, "status"), _latest(ev, "assign"), set(ev.loc[ev["type"] == "auto_bounce", "complaint_id"])
    df["workflow_status"] = df["complaint_id"].map(status).fillna("new")
    df = df[df["workflow_status"] != "resolved"]
    df["owner_team"] = df["complaint_id"].map(owner).fillna(df["category"].map(router.TEAMS))
    df["notes"] = df["complaint_id"].map(ev[ev["type"] == "note"].groupby("complaint_id").size()).fillna(0).astype(int)

    alerts = context.active_alerts()
    flags = [context.alert_for(r, c, alerts) for r, c in zip(df["region"], df["category"])]
    df["alert_id"] = [f["alert_id"] if f else None for f in flags]
    df["alert_summary"] = [f["summary"] if f else None for f in flags]

    scored = queue_score.score_frame(df, build_baselines.load()["breach_survival"],
                                     alert_flags=[f is not None for f in flags])
    scored["info_only_likelihood"] = info_only_rates(scored)
    scored["auto_template"] = scored["category"].map(AUTO_TEMPLATES)
    scored["in_auto_lane"] = (
        (scored["info_only_likelihood"] >= AUTO_THRESHOLD)
        & scored["auto_template"].notna()
        & (scored["age_days"] <= AUTO_MAX_AGE)
        & ~scored["complaint_id"].isin(bounced)
        & (scored["workflow_status"] == "new")
    )
    scored["bounced_from_auto"] = scored["complaint_id"].isin(bounced)
    if not include_auto:
        scored = scored[~scored["in_auto_lane"]]
    return scored


ROW_FIELDS = [
    "complaint_id", "priority", "category", "region", "channel", "source_system", "account_id",
    "date_opened", "sla_days", "age_days", "overdue_days", "overdue_ratio", "overdue_state",
    "breach_risk", "transferred_between_systems", "owner_team", "workflow_status", "alert_id",
    "alert_summary", "queue_score", "why", "from_intake", "notes", "bounced_from_auto",
    "info_only_likelihood",
]


def rows(df):
    df = df.copy()
    df["date_opened"] = df["date_opened"].dt.strftime("%Y-%m-%d")
    df["transferred_between_systems"] = df["transferred_between_systems"].fillna(0).astype(int)
    df["from_intake"] = df["from_intake"].fillna(False).astype(bool)
    df = df.astype(object).where(df.notna(), None)
    return [{k: r[k] for k in ROW_FIELDS} for r in df.to_dict("records")]


def queue(strict=False, filters=None, limit=None, offset=0):
    scored = open_cases()
    for key, val in (filters or {}).items():
        if not val:
            continue
        if key == "search":
            s = val.upper()
            scored = scored[scored["account_id"].str.upper().str.contains(s) | scored["complaint_id"].str.contains(s)]
        elif key == "system":
            scored = scored[scored["source_system"] == val]
        elif key == "owner":
            scored = scored[scored["owner_team"] == val]
        else:
            scored = scored[scored[key] == val]
    ranked = queue_score.rank(scored, strict=strict)
    ranked = ranked.assign(rank=range(1, len(ranked) + 1))
    total = len(ranked)
    page = ranked.iloc[offset: offset + limit if limit else None]
    out = rows(page)
    for r, rk in zip(out, page["rank"]):
        r["rank"] = int(rk)
    summary = {
        "total": total,
        "by_priority": scored["priority"].value_counts().to_dict(),
        "breached": int(scored["breached"].sum()),
        "amber": int((scored["overdue_state"] == "amber").sum()),
        "median_overdue_days": float(scored["overdue_days"].median()) if total else 0,
        "max_overdue_days": int(scored["overdue_days"].max()) if total else 0,
        "stored_flag_breached_share": float(
            scored.loc[~scored["from_intake"].astype(bool), "sla_breach"].fillna(0).mean()) if total else 0,
        "from_intake": int(scored["from_intake"].astype(bool).sum()),
    }
    return {"rows": out, "summary": summary, "config": queue_score.config(), "strict": strict}


def auto_lane():
    df = open_cases(include_auto=True)
    lane = df[df["in_auto_lane"]].sort_values("date_opened", ascending=False)
    bounced = df[df["bounced_from_auto"]]
    out = rows(lane)
    for r, t in zip(out, lane["auto_template"]):
        r["auto_template"] = t
        r["watch_until"] = (pd.Timestamp(r["date_opened"]) + pd.Timedelta(days=AUTO_WATCH_DAYS)).strftime("%Y-%m-%d")
    return {"rows": out, "bounced": rows(bounced), "threshold": AUTO_THRESHOLD,
            "templates": AUTO_TEMPLATES, "watch_days": AUTO_WATCH_DAYS}


def case_detail(complaint_id):
    df = open_cases(include_auto=True)
    hit = df[df["complaint_id"] == complaint_id]
    allc = context.all_complaints()
    if hit.empty:
        src = allc[allc["complaint_id"] == complaint_id]
        if src.empty:
            return None
        row = src.iloc[0]
        case = {"complaint_id": complaint_id, "status": row["status"], "closed": True}
    else:
        row = hit.iloc[0]
        case = rows(hit)[0]
        in_queue = queue_score.rank(df[~df["in_auto_lane"]])
        ids = list(in_queue["complaint_id"])
        case["rank"] = ids.index(complaint_id) + 1 if complaint_id in ids else None
        case["in_auto_lane"] = bool(row["in_auto_lane"])
        case["watch_until"] = (pd.Timestamp(case["date_opened"]) + pd.Timedelta(days=AUTO_WATCH_DAYS)).strftime("%Y-%m-%d")
        case["auto_template"] = row["auto_template"] if row["in_auto_lane"] else None

    entry = row["source_system"]
    if row.get("from_intake") and isinstance(row.get("triage"), str):
        # Routed intakes live in CaseTrack; compare against the system they actually arrived in.
        entry = json.loads(row["triage"])["legacy_route"]["entry_system"].split()[0]
    intake = {"complaint_id": complaint_id, "channel": row["channel"], "category": row["category"],
              "priority": row["priority"], "region": row["region"], "account_id": row["account_id"],
              "entry_system": entry}
    triage = router.route(intake, build_baselines.load(), context.gather(intake, allc))
    if "queue_score" in row:
        triage["queue_score"] = float(row["queue_score"])

    hist = context.account_history(row["account_id"], complaint_id, allc)
    history = [{
        "complaint_id": h.complaint_id, "date_opened": h.date_opened.strftime("%Y-%m-%d"),
        "date_closed": h.date_closed.strftime("%Y-%m-%d") if pd.notna(h.date_closed) else None,
        "status": h.status, "category": h.category, "priority": h.priority,
        "transferred": bool(h.transferred_between_systems), "reopened": bool(h.reopened),
        "resolution_action": h.resolution_action if isinstance(h.resolution_action, str) else None,
        "days_to_close": None if pd.isna(h.days_to_close) else int(h.days_to_close),
    } for h in hist.itertuples()]

    ev = _events()
    events = ev[ev["complaint_id"] == complaint_id].to_dict("records")
    alert = None
    if triage["context"]["region_alert_id"]:
        from jobs.detect_alerts import load_alerts
        alert = next((a for a in load_alerts() if a["alert_id"] == triage["context"]["region_alert_id"]), None)
    summary = case_summary(case, triage, history, alert) if not case.get("closed") else None
    return {"case": case, "triage": triage, "history": history, "events": events, "alert": alert, "summary": summary}


FIELD_ACTIONS = {"Meter visit required", "Field repair required", "Appointment rebooked by agent"}


def case_summary(case, triage, history, alert):
    """The four questions an agent needs answered first, from deterministic rules (no model)."""
    top = (triage["resolution_path"] or [{}])[0]
    due = (pd.Timestamp(case["date_opened"]) + pd.Timedelta(days=int(case["sla_days"]))).strftime("%Y-%m-%d")
    od = case["overdue_days"]
    timing = f"{od} days past its {case['sla_days']}-day SLA" if od > 0 else (
        "due today" if od == 0 else f"{-od} days left of its {case['sla_days']}-day SLA")
    what = (f"{case['category']} complaint via {case['channel']} in {case['region']}, opened {case['date_opened']} "
            f"({case['age_days']} days ago); {timing} (due {due}).")
    if case["transferred_between_systems"]:
        what += " It has already been transferred between systems."

    status = case["workflow_status"]
    action = top.get("action", "Review the complaint")
    share = f"{top['share']:.0%} of similar cases" if top else "no history"
    if case.get("in_auto_lane"):
        nxt = f"No agent action: an automatic answer was sent; watching for a reply until {case.get('watch_until') or 'the 7-day window ends'}."
    elif status == "escalated":
        nxt = f"Senior review, then most likely '{action}' ({share})."
    elif status == "in_progress":
        nxt = f"Complete '{action}' ({share}) and confirm the outcome with the customer."
    else:
        med = f"; median {top['median_days']:.0f} days historically" if top else ""
        nxt = f"Pick it up and start on '{action}' ({share}{med})."

    blockers = []
    if status == "escalated":
        blockers.append("Escalated: waiting on a senior decision.")
    if od > 0:
        blockers.append(f"Past SLA by {od} days: counts against the regulator score.")
    if case["transferred_between_systems"]:
        blockers.append("Transferred between systems: CaseTrack loses history on transfer, so check the account history below.")
    if action in FIELD_ACTIONS:
        blockers.append("Likely needs a field visit: FieldForce has no link to CaseTrack, so attach the case history to the job.")
    if alert:
        blockers.append(f"Part of a regional pattern ({alert['detail']['summary']}): the investigation may explain the root cause.")
    prior = len(history)
    if prior:
        blockers.append(f"Repeat complainant: {prior} earlier complaint{'s' if prior > 1 else ''} on this account.")
    if not blockers:
        blockers.append("Nothing blocking: ready to work.")
    return {
        "what_happened": what,
        "next_action": nxt,
        "owner": f"{case['owner_team']} in {triage['owner']['system']}",
        "blockers": blockers,
        "due_date": due,
    }


def add_event(complaint_id, typ, value=None, note=None):
    if typ not in EVENT_TYPES:
        raise ValueError(f"unknown event type {typ}")
    if typ == "status" and value not in STATUSES:
        raise ValueError(f"unknown status {value}")
    now = datetime.now().isoformat(timespec="seconds")
    with db.store().transaction() as tx:
        tx.execute("INSERT INTO case_events (complaint_id, ts, type, value, note) VALUES (?,?,?,?,?)",
                   (complaint_id, now, typ, value, note))
        if typ == "customer_help":
            # The customer said the update didn't solve it: escalate so it rises in the queue.
            tx.execute("INSERT INTO case_events (complaint_id, ts, type, value, note) VALUES (?,?,?,?,?)",
                       (complaint_id, now, "status", "escalated", "Customer asked for more help after an update"))


def _next_id(tx):
    src_max = int(db.complaints()["complaint_id"].str[3:].astype(int).max())
    rows = tx.query("SELECT MAX(CAST(SUBSTR(complaint_id, 4) AS INTEGER)) AS m FROM intake_complaints")
    return f"NW-{max(src_max, rows[0]['m'] or 0) + 1}"


def create_intake(intake):
    """Route a new complaint and add it to the queue. Returns the TriageResult."""
    store = db.store()
    with store.transaction() as tx:
        cid = _next_id(tx)
    intake = {**intake, "complaint_id": cid}
    intake["entry_system"] = intake.get("entry_system") or router.CHANNEL_ENTRY.get(intake["channel"], "SYS-05")
    triage = router.route_live(intake)
    store.execute(
        "INSERT INTO intake_complaints VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (cid, db.AS_OF.isoformat(), intake["channel"], intake["category"], intake["priority"],
         intake["region"], "SYS-04", intake.get("account_id") or f"ACC-{900000 + int(cid[3:]) % 99999}",
         router.SLA_DAYS[intake["priority"]], json.dumps(triage), datetime.now().isoformat(timespec="seconds")),
    )
    scored = queue_score.rank(open_cases())
    pos = list(scored["complaint_id"]).index(cid) + 1 if cid in set(scored["complaint_id"]) else None
    triage["queue_rank"] = pos
    triage["queue_size"] = len(scored)
    triage["in_auto_lane"] = pos is None
    return triage


def reset_demo():
    """Clear everything the demo created (intake complaints, events, simulated alerts and signal points)."""
    from jobs.detect_alerts import reset_scenario
    with db.store().transaction() as tx:
        tx.execute("DELETE FROM intake_complaints")
        tx.execute("DELETE FROM case_events")
    reset_scenario()
