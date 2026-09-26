"""Precompute the learned lookup tables the router and queue use, into app.db `baselines`.

Run:  python -m engine.build_baselines

Every table is a small, explainable aggregate. Only attributes known at intake are used as
keys; outcome fields (days_to_close, sla_breach, reopened, ...) only ever appear as targets.
"""

import json

import numpy as np
import pandas as pd

from engine import cost_model, db

RECENT_MONTHS = 12      # closed cases opened in the last 12 months count double
RECENT_WEIGHT = 2.0
INFO_SMOOTHING = 50     # pseudo-count pulling small (category, channel) groups to the category rate
SURVIVAL_WINDOW = 12    # months of intake used for the breach-survival curves


def _weights(df):
    cutoff = db.AS_OF_TS - pd.DateOffset(months=RECENT_MONTHS)
    return np.where(df["date_opened"] >= cutoff, RECENT_WEIGHT, 1.0)


def _wmean(values, weights):
    return float(np.average(values, weights=weights)) if len(values) else None


def resolution_paths(closed):
    """(category, priority) -> distribution of resolution actions, from non-transferred cases."""
    base = closed[closed["transferred_between_systems"] == 0].copy()
    base["w"] = _weights(base)
    out = {}
    for keys, g in list(base.groupby(["category", "priority"])) + [
        ((cat, "*"), g) for cat, g in base.groupby("category")
    ]:
        total = g["w"].sum()
        rows = []
        for action, a in g.groupby("resolution_action"):
            rows.append({
                "action": action,
                "share": float(a["w"].sum() / total),
                "median_days": float(a["days_to_close"].median()),
                "reopen_rate": _wmean(a["reopened"], a["w"]),
                "n": int(len(a)),
            })
        rows.sort(key=lambda r: -r["share"])
        out["|".join(keys)] = rows
    return out


def info_only(closed):
    """(category, channel) -> smoothed rate of 'resolvable by information only'."""
    out = {}
    for cat, g in closed.groupby("category"):
        cat_rate = float(g["resolvable_by_information_only"].mean())
        out[f"{cat}|*"] = {"rate": cat_rate, "n": int(len(g)), "category_rate": cat_rate}
        for ch, h in g.groupby("channel"):
            n = len(h)
            rate = (h["resolvable_by_information_only"].sum() + INFO_SMOOTHING * cat_rate) / (n + INFO_SMOOTHING)
            out[f"{cat}|{ch}"] = {"rate": float(rate), "n": int(n), "category_rate": cat_rate}
    return out


def outcomes(closed):
    """(category, priority, transferred) -> expected days, breach and reopen rates."""
    df = closed.copy()
    df["w"] = _weights(df)
    out = {}
    groups = list(df.groupby(["category", "priority", "transferred_between_systems"]))
    groups += [((c, "*", t), g) for (c, t), g in df.groupby(["category", "transferred_between_systems"])]
    for (cat, pri, t), g in groups:
        out[f"{cat}|{pri}|{int(t)}"] = {
            "mean_days": _wmean(g["days_to_close"], g["w"]),
            "median_days": float(g["days_to_close"].median()),
            "breach": _wmean(g["sla_breach"], g["w"]),
            "reopen": _wmean(g["reopened"], g["w"]),
            "n": int(len(g)),
        }
    return out


def transfer_rates(all_complaints):
    """entry system -> historical transfer rate (all complaints, open ones included)."""
    out = {}
    for sys_id, g in all_complaints.groupby("source_system"):
        out[sys_id] = {
            "rate": float(g["transferred_between_systems"].mean()),
            "n": int(len(g)),
            "by_category": {c: float(h["transferred_between_systems"].mean())
                            for c, h in g.groupby("category")},
        }
    return out


def breach_survival(all_complaints):
    """(priority, transferred) -> P(breach | still open at age a), for a = 0 .. 3 x SLA.

    Kaplan-Meier over the last 12 months of intake, with open cases treated as censored at
    their current age, so the still-open recent backlog is counted rather than dropped.
    """
    cutoff = db.AS_OF_TS - pd.DateOffset(months=SURVIVAL_WINDOW)
    df = all_complaints[all_complaints["date_opened"] >= cutoff].copy()
    age = (db.AS_OF_TS - df["date_opened"]).dt.days
    df["t"] = np.where(df["is_open"], age, df["days_to_close"])
    df["event"] = (~df["is_open"]).astype(int)
    out = {}
    for (pri, tr), g in df.groupby(["priority", "transferred_between_systems"]):
        sla = int(g["sla_days"].iloc[0])
        horizon = sla * 3
        t, e = g["t"].to_numpy(), g["event"].to_numpy()
        surv, s = [], 1.0
        for d in range(0, horizon + 2):
            # S(d) = P(T > d)
            at_risk = (t >= d).sum()
            closes = ((t == d) & (e == 1)).sum()
            if at_risk:
                s *= 1 - closes / at_risk
            surv.append(s)
        s_sla = surv[sla]
        cond = [float(min(1.0, s_sla / surv[a])) if surv[a] > 0 else 1.0 for a in range(sla + 1)]
        out[f"{pri}|{int(tr)}"] = {"sla_days": sla, "p_breach_given_age": cond, "n": int(len(g))}
    return out


def region_signals():
    mr = db.meter_reads()
    latest = mr["month"].max()
    out = {}
    for region, g in mr.groupby("region"):
        cur = g[g["month"] == latest].iloc[0]
        out[region] = {
            "month": latest,
            "accounts": int(cur["accounts"]),
            "estimated_read_rate": float(cur["estimated_read_rate"]),
            "smart_meter_penetration": float(cur["smart_meter_penetration"]),
            "exceptions_per_1k": float(cur["exceptions_per_1k"]),
            "systems": cur["systems_serving_region"].split("/"),
        }
    return out


def build():
    allc = db.complaints()
    closed = allc[~allc["is_open"]]
    tables = {
        "resolution_path": resolution_paths(closed),
        "info_only": info_only(closed),
        "outcomes": outcomes(closed),
        "transfer_rate": transfer_rates(allc),
        "breach_survival": breach_survival(allc),
        "region_signals": region_signals(),
        "global": {"transfer_penalty": cost_model.transfer_penalty(), "as_of": str(db.AS_OF)},
    }
    conn = db.app_conn()
    with conn:
        conn.execute("DELETE FROM baselines")
        conn.executemany(
            "INSERT INTO baselines (kind, key, value) VALUES (?, ?, ?)",
            [(kind, key, db.dumps(val)) for kind, t in tables.items() for key, val in t.items()],
        )
    conn.close()
    load.cache_clear()
    return tables


_cache = {}


def load():
    """kind -> {key: value}. Builds the table on first use if it's empty."""
    if "tables" not in _cache:
        conn = db.app_conn()
        rows = conn.execute("SELECT kind, key, value FROM baselines").fetchall()
        conn.close()
        if not rows:
            _cache["tables"] = build()
        else:
            tables = {}
            for r in rows:
                tables.setdefault(r["kind"], {})[r["key"]] = json.loads(r["value"])
            _cache["tables"] = tables
    return _cache["tables"]


load.cache_clear = _cache.clear


if __name__ == "__main__":
    t = build()
    for kind, v in t.items():
        print(f"{kind:18s} {len(v):4d} keys")
