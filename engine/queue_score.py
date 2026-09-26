"""Triage Queue ranking (#2).

All timing is computed from dates as of AS_OF; the stored sla_breach flag is never used for
open tickets (it marks 98% of them as breached, which the dates don't support).

    age_days      = as_of - date_opened
    overdue_days  = age_days - sla_days            (negative: still inside SLA)
    overdue_ratio = overdue_days / sla_days        (puts P1 and P3 on the same scale)
    imminence     = 1 - days_left / horizon        (horizon = 20 days, the longest SLA)
    breach_risk   = P(breach | still open at this age), Kaplan-Meier, from baselines

    breached:     score = w_p * (1 + overdue_ratio)
    not breached: score = w_p * breach_risk * imminence
    + transferred_bonus if transferred, + alert_bonus if a live regional alert covers it
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from engine import db

CONFIG_PATH = Path(__file__).with_name("queue_config.json")


def config():
    return json.loads(CONFIG_PATH.read_text())


def _breach_risk(priority, transferred, age, survival):
    curve = survival.get(f"{priority}|{int(transferred)}")
    if curve is None:
        return 1.0
    p = curve["p_breach_given_age"]
    return p[min(max(int(age), 0), len(p) - 1)]


def score_frame(df, survival, cfg=None, as_of=None, alert_flags=None):
    """Add timing, score and reason columns to a frame of open complaints."""
    cfg = cfg or config()
    as_of = pd.Timestamp(as_of or db.AS_OF)
    out = df.copy()
    out["age_days"] = (as_of - pd.to_datetime(out["date_opened"])).dt.days
    out["overdue_days"] = out["age_days"] - out["sla_days"]
    out["overdue_ratio"] = out["overdue_days"] / out["sla_days"]
    out["breached"] = out["overdue_days"] > 0
    out["priority_weight"] = out["priority"].map(cfg["priority_weight"]).fillna(1)
    # Measured in absolute days to the deadline, not as a share of the SLA: the plan's
    # 1 - days_left / sla_days is 0 for every fresh case, so a new P1 (5 days left) would tie a
    # new P3 (20 days left) at the bottom of the queue.
    out["imminence"] = (1 - (-out["overdue_days"]) / cfg["imminence_horizon_days"]).clip(0, 1)
    out["breach_risk"] = [
        1.0 if b else _breach_risk(p, t, a, survival)
        for p, t, a, b in zip(out["priority"], out["transferred_between_systems"], out["age_days"], out["breached"])
    ]
    out["alert"] = False if alert_flags is None else alert_flags
    base = np.where(
        out["breached"],
        out["priority_weight"] * (1 + out["overdue_ratio"]),
        out["priority_weight"] * out["breach_risk"] * out["imminence"],
    )
    out["score_base"] = base
    out["score_transfer"] = cfg["transferred_bonus"] * out["transferred_between_systems"].fillna(0)
    out["score_alert"] = cfg["alert_bonus"] * out["alert"].astype(float)
    out["queue_score"] = (out["score_base"] + out["score_transfer"] + out["score_alert"]).round(3)
    out["overdue_state"] = np.select(
        [out["breached"], -out["overdue_days"] <= cfg["amber_days"]], ["red", "amber"], "green"
    )
    out["why"] = [_why(r, cfg) for r in out.itertuples()]
    return out


def _why(r, cfg):
    w = int(r.priority_weight)
    if r.breached:
        parts = [f"{r.priority} is {int(r.overdue_days)} days past its {int(r.sla_days)}-day SLA: "
                 f"weight {w} x (1 + {r.overdue_ratio:.2f} overdue ratio) = {r.score_base:.2f}"]
    else:
        left = -int(r.overdue_days)
        parts = [f"{r.priority} has {left} day{'s' if left != 1 else ''} left of its {int(r.sla_days)}-day SLA; "
                 f"{r.breach_risk:.0%} of similar cases still open at day {int(r.age_days)} went on to breach: "
                 f"weight {w} x {r.breach_risk:.2f} risk x {r.imminence:.2f} imminence = {r.score_base:.2f}"]
    if r.score_transfer:
        parts.append(f"+{cfg['transferred_bonus']} transferred (transferred cases breach 88% and reopen 29%)")
    if r.score_alert:
        parts.append(f"+{cfg['alert_bonus']} live regional alert")
    return parts


def rank(scored, strict=False):
    if strict:
        order = scored.assign(_p=scored["priority"].str[1].astype(int))
        return order.sort_values(["_p", "overdue_days"], ascending=[True, False]).drop(columns="_p")
    return scored.sort_values("queue_score", ascending=False)
