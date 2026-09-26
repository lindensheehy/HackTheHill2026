"""Replay (#1B): run the last 6 months of real complaints through the router.

The server returns per-month facts (volumes, actual transfers, what the router would have
done). The savings are applied client-side so the adoption / avoidance sliders are instant:

    avoided   = actual transfers x adoption x avoidance
    saved     = avoided x per_avoided   (GBP 53, 15.2 days, 0.203 reopens, 0.187 breaches)
"""

import random

import pandas as pd

from engine import build_baselines, cost_model, db, router

START = "2026-04"
SAMPLES_PER_MONTH = 24


def replay():
    c = db.complaints()
    window = c[c["month"] >= START].sort_values("date_opened")
    tables = build_baselines.load()
    rates = {k: (0.0 if k == router.CASE_SYSTEM else v["rate"]) for k, v in tables["transfer_rate"].items()}
    rng = random.Random(7)
    months = []
    for m, g in window.groupby("month"):
        sample = g.iloc[sorted(rng.sample(range(len(g)), min(SAMPLES_PER_MONTH, len(g))))]
        ticker = []
        for r in sample.itertuples():
            t = router.route({"complaint_id": r.complaint_id, "channel": r.channel, "category": r.category,
                              "priority": r.priority, "region": r.region, "entry_system": r.source_system},
                             tables, {})
            ticker.append({"id": r.complaint_id, "date": r.date_opened.strftime("%Y-%m-%d"),
                           "category": r.category, "priority": r.priority, "region": r.region,
                           "entry": r.source_system, "team": t["owner"]["team"],
                           "transferred": bool(r.transferred_between_systems),
                           "days_saved": round(t["expected_days"]["legacy"] - t["expected_days"]["routed"], 1)})
        weeks = g.groupby(g["date_opened"].dt.to_period("W").dt.start_time)
        months.append({
            "month": m,
            "complaints": int(len(g)),
            "outside_casetrack": int((g["source_system"] != router.CASE_SYSTEM).sum()),
            "actual_transfers": int(g["transferred_between_systems"].sum()),
            "expected_transfers": round(float(g["source_system"].map(rates).sum()), 1),
            "weeks": [{"week": w.strftime("%Y-%m-%d"), "complaints": int(len(x)),
                       "transfers": int(x["transferred_between_systems"].sum())} for w, x in weeks],
            "ticker": ticker,
        })
    tp = cost_model.transfer_penalty()
    cutoff = db.AS_OF_TS - pd.DateOffset(months=12)
    last12 = int(c[c["date_opened"] > cutoff]["transferred_between_systems"].sum())
    return {
        "months": months,
        "per_avoided": tp["per_avoided"],
        "defaults": {"adoption": 0.8, "avoidance": 0.6},
        "annual_transfers": last12,
        "total_complaints": int(len(window)),
    }
