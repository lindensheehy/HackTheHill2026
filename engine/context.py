"""Context the router and queue attach to a complaint: account history and live regional alerts."""

import pandas as pd

from engine import db


def all_complaints():
    """Source complaints plus anything created through the Intake Simulator."""
    src = db.complaints()
    conn = db.app_conn()
    new = pd.read_sql("SELECT * FROM intake_complaints", conn)
    conn.close()
    if new.empty:
        src["from_intake"] = False
        return src
    new["date_opened"] = pd.to_datetime(new["date_opened"])
    new["date_closed"] = pd.NaT
    new["status"] = "Open"
    new["is_open"] = True
    new["transferred_between_systems"] = 0
    new["reopened"] = 0
    new["month"] = new["date_opened"].dt.strftime("%Y-%m")
    new["from_intake"] = True
    src["from_intake"] = False
    src["triage"] = None
    return pd.concat([src, new[[c for c in new.columns if c in src.columns or c == "triage"]]],
                     ignore_index=True)


def account_history(account_id, exclude_id=None, df=None):
    df = all_complaints() if df is None else df
    h = df[(df["account_id"] == account_id) & (df["complaint_id"] != exclude_id)]
    return h.sort_values("date_opened")


def active_alerts():
    from jobs.detect_alerts import load_alerts
    return load_alerts(status="active")


def alert_for(region, category, alerts=None):
    """Strongest active alert that covers this region and relates to this category."""
    alerts = active_alerts() if alerts is None else alerts
    hits = [a for a in alerts
            if region in a["regions"] and category in a["detail"].get("related_categories", [])]
    if not hits:
        return None
    a = max(hits, key=lambda a: a["z"])
    return {"alert_id": a["alert_id"], "summary": f"{a['detail']['summary']} (z = {a['z']:.1f})",
            "synthetic": bool(a["synthetic"])}


def gather(intake, df=None, alerts=None):
    prior = 0
    if intake.get("account_id"):
        prior = len(account_history(intake["account_id"], intake.get("complaint_id"), df))
    return {
        "account_prior_complaints": prior,
        "region_alert": alert_for(intake["region"], intake["category"], alerts),
    }
