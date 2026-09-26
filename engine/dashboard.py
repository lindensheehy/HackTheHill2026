"""Operations Dashboard (#3) aggregates. Every function returns plain JSON-able dicts."""

import numpy as np
import pandas as pd

from engine import cost_model, db

INCOMPLETE_OPEN_SHARE = 0.05   # opening cohorts with more than 5% still open are marked incomplete
FOCUS_REGIONS = ("Barrowdale", "Dunmoor")


def _f(x, nd=3):
    return None if x is None or pd.isna(x) else round(float(x), nd)


def monthly():
    c = db.complaints()
    k = db.monthly_kpis().set_index("month")
    closed = c[~c["is_open"]]
    g = c.groupby("month")
    out = []
    for m in k.index:
        cohort = closed[closed["month"] == m]
        open_share = float(g.get_group(m)["is_open"].mean()) if m in g.groups else 0
        out.append({
            "month": m,
            "opened": int(k.loc[m, "complaints_opened"]),
            "closed": int(k.loc[m, "complaints_closed"]),
            "avg_days_to_close": _f(k.loc[m, "avg_days_to_close"], 1),
            "fcr": _f(k.loc[m, "first_contact_resolution_rate"]),
            "regulator_score": _f(k.loc[m, "regulator_satisfaction_score_of_5"], 2),
            "inbound_calls": int(k.loc[m, "inbound_calls"]),
            "cost_to_serve": _f(k.loc[m, "cost_to_serve_per_account"], 2),
            "breach_rate": _f(cohort["sla_breach"].mean()),
            "transfer_rate": _f(g.get_group(m)["transferred_between_systems"].mean()),
            "open_share": _f(open_share),
            "incomplete": open_share > INCOMPLETE_OPEN_SHARE,
        })
    df = pd.DataFrame(out)
    df["breach_rate_3m"] = df["breach_rate"].rolling(3, min_periods=1).mean().round(3)
    return df.to_dict("records")


def kpi_header():
    months = monthly()
    last, prior = months[-1], months[-13]
    # Breach rate: use the latest complete cohort so the headline isn't flattered by open tickets.
    complete = [m for m in months if not m["incomplete"]]
    lc, pc = complete[-1], next(m for m in months if m["month"] == _minus_year(complete[-1]["month"]))

    def tile(key, label, fmt, cur, prev, better="down", series_from=months):
        return {"key": key, "label": label, "format": fmt, "value": cur[key], "prior": prev[key],
                "month": cur["month"], "prior_month": prev["month"], "better": better,
                "series": [{"month": m["month"], "v": m[key]} for m in series_from]}

    return {
        "as_of": str(db.AS_OF),
        "tiles": [
            tile("opened", "Complaints this month", "int", last, prior),
            tile("avg_days_to_close", "Avg days to close", "days", last, prior),
            tile("breach_rate", "SLA breach rate", "pct", lc, pc, series_from=complete),
            tile("fcr", "First-contact resolution", "pct", last, prior, better="up"),
            tile("regulator_score", "Regulator score (of 5)", "score", last, prior, better="up"),
        ],
        "penalty_per_quarter": cost_model.cost("regulator_penalty_quarter"),
        "first": {"breach_rate": months[0]["breach_rate"], "avg_days_to_close": months[0]["avg_days_to_close"],
                  "regulator_score": months[0]["regulator_score"], "opened": months[0]["opened"]},
    }


def _minus_year(m):
    return (pd.Period(m, "M") - 12).strftime("%Y-%m")


def transfer_panel():
    c = db.complaints()
    closed = c[~c["is_open"]]
    tp = cost_model.transfer_penalty()
    p99 = closed["days_to_close"].quantile(0.99)
    slow = closed[closed["days_to_close"] > p99]
    by_entry = [{"system": s, "name": db.system_names()[s], "rate": _f(g["transferred_between_systems"].mean()),
                 "n": int(len(g))} for s, g in c.groupby("source_system")]
    outside = c[c["source_system"] != "SYS-04"]
    spread = {}
    for dim in ("category", "channel", "priority", "region"):
        r = outside.groupby(dim)["transferred_between_systems"].mean()
        spread[dim] = {"min": _f(r.min()), "max": _f(r.max()),
                       "values": {k: _f(v) for k, v in r.items()}}
    cutoff = db.AS_OF_TS - pd.DateOffset(months=12)
    last12 = int(c[(c["date_opened"] > cutoff)]["transferred_between_systems"].sum())
    per = tp["per_avoided"]
    return {
        "penalty": tp,
        "slowest_1pct": {"threshold_days": _f(p99, 0), "n": int(len(slow)),
                         "transferred_share": _f(slow["transferred_between_systems"].mean())},
        "by_entry_system": by_entry,
        "spread_outside_casetrack": spread,
        "last_12m": {
            "transfers": last12,
            "gbp": round(last12 * per["gbp"]),
            "days": round(last12 * per["days"]),
            "reopens": round(last12 * per["reopens"]),
            "breaches": round(last12 * per["breaches"]),
        },
    }


def regions():
    c = db.complaints()
    mr = db.meter_reads()
    reg_sys = db.region_systems()
    names = db.system_names()
    cutoff = db.AS_OF_TS - pd.DateOffset(months=12)
    last12 = c[c["date_opened"] > cutoff]
    closed12 = last12[~last12["is_open"]]
    latest = mr[mr["month"] == mr["month"].max()].set_index("region")
    first = mr[mr["month"] == mr["month"].min()].set_index("region")
    mr12 = mr[mr["month"] > cutoff.strftime("%Y-%m")]
    billing_cats = {"Billing - disputed amount", "Billing - estimated read", "Metering - no read taken"}
    out = []
    for region in sorted(latest.index):
        lc, rc = last12[last12["region"] == region], closed12[closed12["region"] == region]
        acc = float(latest.loc[region, "accounts"])
        bill = c[c["region"] == region]["bill_correction_value"].sum()
        out.append({
            "region": region,
            "focus": region in FOCUS_REGIONS,
            "accounts": int(acc),
            "complaints_12m": int(len(lc)),
            "complaints_per_1k": _f(len(lc) / acc * 1000, 2),
            "billing_complaints_per_1k": _f(lc["category"].isin(billing_cats).sum() / acc * 1000, 2),
            "breach_rate": _f(rc["sla_breach"].mean()),
            "transfer_rate": _f(lc["transferred_between_systems"].mean()),
            "estimated_read_rate": _f(latest.loc[region, "estimated_read_rate"]),
            "smart_meter_penetration": _f(latest.loc[region, "smart_meter_penetration"]),
            "smart_meter_start": _f(first.loc[region, "smart_meter_penetration"]),
            "exceptions_per_1k": _f(mr12[mr12["region"] == region]["exceptions_per_1k"].mean(), 1),
            "bill_correction_value": round(float(bill)),
            "open_now": int(c[(c["region"] == region) & c["is_open"]].shape[0]),
            "systems": [{"id": s, "name": names.get(s, s)} for s in reg_sys.get(region, [])],
        })
    total_bill = sum(r["bill_correction_value"] for r in out)
    for r in out:
        r["bill_correction_share"] = _f(r["bill_correction_value"] / total_bill)
    trend = [{"month": m, **{r: _f(v, 3) for r, v in g.set_index("region")["estimated_read_rate"].items()}}
             for m, g in mr.groupby("month")]
    return {"regions": out, "estimated_read_trend": trend}


def heatmap():
    c = db.complaints()
    t = c.groupby(["category", "month"]).size().unstack(fill_value=0)
    months = list(t.columns)
    rows = []
    for cat, r in t.iterrows():
        mean = r.mean()
        rows.append({"category": cat, "counts": [int(v) for v in r], "index": [_f(v / mean, 2) for v in r]})
    return {"months": months, "rows": sorted(rows, key=lambda r: -sum(r["counts"]))}


def graph(alerts=None):
    """Regions, systems and how they connect, for the dependency graph."""
    c = db.complaints()
    sysdf = db.systems().set_index("system_id")
    reg_sys = db.region_systems()
    alerts = alerts or []
    alert_regions = {r for a in alerts for r in a["regions"]}
    alert_systems = {s for a in alerts for s in a["shared_systems"]}
    entry = c.groupby("source_system").agg(n=("complaint_id", "size"), rate=("transferred_between_systems", "mean"))
    used = set(entry.index) | {s for v in reg_sys.values() for s in v} | {"SYS-08", "SYS-09", "SYS-10", "SYS-14"}
    nodes = []
    for sid in sorted(used):
        s = sysdf.loc[sid]
        nodes.append({"id": sid, "kind": "system", "label": s["system_name"], "alert": sid in alert_systems,
                      "entry": sid in entry.index,
                      "info": {k: (s[k].item() if hasattr(s[k], "item") else s[k]) for k in
                               ("purpose", "year_installed", "vendor", "tech_stack", "integration_method",
                                "annual_run_cost", "owning_function", "notes")}})
    for region in sorted(reg_sys):
        nodes.append({"id": region, "kind": "region", "label": region, "alert": region in alert_regions,
                      "focus": region in FOCUS_REGIONS})
    edges = []
    for region, ss in reg_sys.items():
        for s in ss:
            edges.append({"source": region, "target": s, "kind": "served_by"})
    for sid, r in entry.iterrows():
        if sid != "SYS-04":
            edges.append({"source": sid, "target": "SYS-04", "kind": "transfers_to",
                          "label": f"{r['rate']:.0%} transferred", "n": int(r["n"])})
    return {"nodes": nodes, "edges": edges}


def smart_meter():
    """Inputs for the smart-meter projection (talking point #6); the chart itself runs client-side."""
    reg = {r["region"]: r for r in regions()["regions"]}
    focus = [reg[r] for r in FOCUS_REGIONS]
    other = [r for k, r in reg.items() if k not in FOCUS_REGIONS]
    acc_f = sum(r["accounts"] for r in focus)
    acc_o = sum(r["accounts"] for r in other)
    wavg = lambda rs, k: sum(r[k] * r["accounts"] for r in rs) / sum(r["accounts"] for r in rs)
    mr = db.meter_reads()
    smart = mr[~mr["region"].isin(FOCUS_REGIONS)]
    corr = float(np.corrcoef(smart["smart_meter_penetration"], smart["estimated_read_rate"])[0, 1])
    exc_gap = (wavg(focus, "exceptions_per_1k") - wavg(other, "exceptions_per_1k")) * acc_f / 1000 * 12
    comp_gap = (wavg(focus, "billing_complaints_per_1k") - wavg(other, "billing_complaints_per_1k")) * acc_f / 1000
    c = db.complaints()
    bill_focus = c[c["region"].isin(FOCUS_REGIONS)]["bill_correction_value"].sum() / 2
    bill_other_rate = c[~c["region"].isin(FOCUS_REGIONS)]["bill_correction_value"].sum() / 2 / acc_o
    meter_visits = int((c["resolution_action"] == "Meter visit required").sum())
    return {
        "accounts_focus": acc_f,
        "meter_cost": cost_model.cost("smart_meter"),
        "target_coverage": 0.30,
        "complaint_cost": cost_model.cost("complaint"),
        "manual_correction_cost": cost_model.cost("bill_correction"),
        "field_visit_cost": cost_model.cost("field_visit"),
        "exceptions_avoided_per_year": round(exc_gap),
        "complaints_avoided_per_year": round(comp_gap),
        "excess_bill_correction_per_year": round(bill_focus - bill_other_rate * acc_f),
        "meter_visits_2y": meter_visits,
        "estimated_read": {"focus": _f(wavg(focus, "estimated_read_rate")), "other": _f(wavg(other, "estimated_read_rate"))},
        "exceptions_per_1k": {"focus": _f(wavg(focus, "exceptions_per_1k"), 1), "other": _f(wavg(other, "exceptions_per_1k"), 1)},
        "penetration_vs_estimated_corr": _f(corr, 2),
        "scatter": [{"region": r.region, "month": r.month, "pen": _f(r.smart_meter_penetration),
                     "est": _f(r.estimated_read_rate)} for r in mr.itertuples()],
    }


def talking_points():
    c = db.complaints()
    closed = c[~c["is_open"]]
    io = closed.groupby("category")["resolvable_by_information_only"].mean().sort_values(ascending=False)
    per_year = closed["resolvable_by_information_only"].sum() / 2
    pilot = db.ai_pilot()
    return {
        "info_only": {
            "share": _f(closed["resolvable_by_information_only"].mean()),
            "per_year": round(per_year),
            "by_category": {k: _f(v) for k, v in io.items()},
            "reopen": {"info_only": _f(closed[closed["resolvable_by_information_only"] == 1]["reopened"].mean()),
                       "other": _f(closed[closed["resolvable_by_information_only"] == 0]["reopened"].mean())},
            "half_saving": round(per_year / 2 * cost_model.cost("complaint")),
        },
        "ai_pilot": pilot.to_dict("records"),
        "ai_pilot_cost": cost_model.cost("ai_pilot"),
    }
