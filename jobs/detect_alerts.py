"""Early-warning alerts (#3): spot unusual signals per region, then connect the dots.

Run:  python -m jobs.detect_alerts

Storage: the panel lives in the `signal_points` table (a TimescaleDB hypertable on Tiger Cloud). Rows have a
source: `derived` (rebuilt from the source tables), `ingest` (POST /api/signals, the live feed) or `simulated`
(the demo scenario, synthetic = 1). Detection always reads the stored feed.

Signals per region and month: complaint count per category, SLA breach rate, billing exceptions
per 1k accounts, estimated read rate. A signal fires when its z-score against the region's own
trailing 6 months is >= 3 (spikes) or when a CUSUM detector crosses its threshold (slow drift).
Alerts on the same signal in the same month in 2+ regions are grouped and tagged with the
systems those regions share.
"""

import hashlib
import json
import math
import re

import numpy as np
import pandas as pd

from engine import db

Z_THRESHOLD = 3.0      # ~1,500 region x signal x month tests: z >= 2 would fire ~40 times by chance
TRAIL = 6
MIN_COUNT = 10           # ignore count spikes on tiny numbers
MIN_LIFT = 1.3           # and require a real effect: >= 30% above the trailing mean
CUSUM_K, CUSUM_H = 0.5, 5.0
BREACH_LAST_MONTH = "2026-08"   # later opening cohorts are too young to judge breach rate
ACTIVE_MONTHS = 2        # alerts from the last N months are "active"

METER_SIGNALS = {
    "exceptions_per_1k": "Billing exceptions per 1k accounts",
    "estimated_read_rate": "Estimated read rate",
}
SIGNAL_CATEGORY = {  # which complaint categories a meter signal relates to
    "exceptions_per_1k": ["Billing - disputed amount", "Billing - estimated read"],
    "estimated_read_rate": ["Billing - estimated read", "Metering - no read taken"],
}


def build_panel(complaints=None, meter=None):
    """Long table: region, month, signal, category, value."""
    c = db.complaints() if complaints is None else complaints
    m = db.meter_reads() if meter is None else meter
    rows = []

    counts = c.groupby(["region", "month", "category"]).size().unstack(fill_value=0).stack()
    for (region, month, cat), v in counts.items():
        rows.append((region, month, f"complaints:{cat}", cat, float(v)))

    c = c.copy()
    age = (db.AS_OF_TS - c["date_opened"]).dt.days
    c["breach_now"] = np.where(c["is_open"], age > c["sla_days"], c["sla_breach"] == 1)
    br = c[c["month"] <= BREACH_LAST_MONTH].groupby(["region", "month"])["breach_now"].mean()
    for (region, month), v in br.items():
        rows.append((region, month, "sla_breach_rate", None, float(v)))

    for r in m.itertuples():
        for sig in METER_SIGNALS:
            rows.append((r.region, r.month, sig, None, float(getattr(r, sig))))
    return pd.DataFrame(rows, columns=["region", "month", "signal", "category", "value"])


def _z_scores(series, counts=False):
    """z of each point vs the trailing TRAIL points (needs a full window).

    Counts get a Poisson floor on the spread (sd >= sqrt(mean)) so small groups don't fire on noise.
    """
    vals = series.to_numpy()
    out = [np.nan] * len(vals)
    for i in range(TRAIL, len(vals)):
        window = vals[i - TRAIL:i]
        mu, sd = window.mean(), window.std(ddof=1)
        sd = max(sd, np.sqrt(mu) if counts else 0.05 * abs(mu), 1e-9)
        out[i] = (vals[i] - mu) / sd
    return out


def _cusum(series):
    """First month where an upward CUSUM on the standardised series crosses CUSUM_H.

    Drift is one event, not a monthly one, so each region fires at most once.
    """
    vals = series.to_numpy()
    base = vals[:TRAIL]
    mu, sd = base.mean(), max(base.std(ddof=1), 0.02)
    s, hits = 0.0, []
    for i in range(TRAIL, len(vals)):
        s = max(0.0, s + (vals[i] - mu) / sd - CUSUM_K)
        if s >= CUSUM_H:
            return [(i, s)]
    return []


def detect(panel, months=None):
    """Raw per-region detections. `months` restricts which months may fire."""
    found = []
    for (region, signal), g in panel.groupby(["region", "signal"]):
        g = g.sort_values("month").reset_index(drop=True)
        cat = g["category"].iloc[0]
        if signal == "sla_breach_rate":
            for i, s in _cusum(g["value"]):
                found.append(dict(region=region, month=g["month"][i], signal=signal, category=cat,
                                  z=float(s), value=float(g["value"][i]), method="cusum",
                                  baseline=float(g["value"][:TRAIL].mean())))
            continue
        is_count = signal.startswith("complaints:")
        zs = _z_scores(g["value"], counts=is_count)
        for i, z in enumerate(zs):
            if np.isnan(z) or z < Z_THRESHOLD:
                continue
            if is_count and (g["value"][i] < MIN_COUNT
                             or g["value"][i] < MIN_LIFT * g["value"][i - TRAIL:i].mean()):
                continue
            found.append(dict(region=region, month=g["month"][i], signal=signal, category=cat,
                              z=float(z), value=float(g["value"][i]), method="zscore",
                              baseline=float(g["value"][i - TRAIL:i].mean())))
    if months is not None:
        found = [f for f in found if f["month"] in months]
    return found


def signal_label(signal):
    if signal.startswith("complaints:"):
        return f"{signal.split(':', 1)[1]} complaints"
    if signal == "sla_breach_rate":
        return "SLA breach rate"
    return METER_SIGNALS.get(signal, signal)


def group(found, synthetic=False):
    """Group same-signal, same-month detections and attach the systems the regions share."""
    reg_sys = db.region_systems()
    names = db.system_names()
    active_from = (db.AS_OF_TS - pd.DateOffset(months=ACTIVE_MONTHS - 1)).strftime("%Y-%m")
    alerts = []
    df = pd.DataFrame(found)
    if df.empty:
        return alerts
    for (month, signal), g in df.groupby(["month", "signal"]):
        regions = sorted(g["region"])
        shared = set.intersection(*(set(reg_sys.get(r, [])) for r in regions))
        shared = sorted(shared)
        label = signal_label(signal)
        verb = "drifting up" if g["method"].iloc[0] == "cusum" else "up"
        where = " and ".join(regions) if len(regions) <= 3 else f"{len(regions)} regions"
        summary = f"{label} {verb} in {where}"
        if len(regions) > 1 and shared:
            summary += "; all served by " + " and ".join(shared)
        system_notes = [
            {"system": f"{s} {names.get(s, '')}", "note": db.systems().set_index("system_id").loc[s, "notes"]}
            for s in shared
        ]
        category = g["category"].iloc[0]
        related = [category] if isinstance(category, str) else SIGNAL_CATEGORY.get(signal, [])
        digest = hashlib.sha1(f"{signal}|{','.join(regions)}".encode()).hexdigest()[:6]
        alert_id = f"{'SIM' if synthetic else 'AL'}-{month}-{digest}"
        alerts.append({
            "alert_id": alert_id,
            "month": month,
            "signal": signal,
            "category": category if isinstance(category, str) else None,
            "regions": regions,
            "z": round(float(g["z"].max()), 2),
            "shared_systems": shared,
            "status": "active" if synthetic or month >= active_from else "historical",
            "synthetic": int(synthetic),
            "detail": {
                "summary": summary,
                "label": label,
                "method": g["method"].iloc[0],
                "related_categories": related,
                "per_region": g[["region", "value", "baseline", "z"]].round(3).to_dict("records"),
                "system_notes": system_notes,
            },
        })
    return alerts


def save(alerts, replace_real=True):
    with db.store().transaction() as tx:
        if replace_real:
            tx.execute("DELETE FROM alerts WHERE synthetic = 0")
        tx.upsert("alerts", ALERT_COLS, [
            (a["alert_id"], a["month"], a["signal"], a["category"], json.dumps(a["regions"]),
             a["z"], json.dumps(a["shared_systems"]), a["status"], a["synthetic"],
             json.dumps(a["detail"])) for a in alerts], key=["alert_id"])
    return alerts


ALERT_COLS = ["alert_id", "month", "signal", "category", "regions", "z", "shared_systems", "status", "synthetic", "detail"]
_SOURCE_RANK = {"derived": 0, "ingest": 1, "simulated": 2}


# ---- The stored signal feed ------------------------------------------------------------------

def _insert_points(tx, df, synthetic, source):
    tx.executemany(
        "INSERT INTO signal_points (time, month, region, signal, category, value, synthetic, source) VALUES (?,?,?,?,?,?,?,?)",
        [(f"{r.month}-01", r.month, r.region, r.signal, r.category if isinstance(r.category, str) else None,
          float(r.value), synthetic, source) for r in df.itertuples()],
    )


def materialize(panel=None):
    """Rebuild the `derived` part of the feed from the source tables. Ingested and simulated points are kept."""
    panel = build_panel() if panel is None else panel
    with db.store().transaction() as tx:
        tx.execute("DELETE FROM signal_points WHERE source = 'derived'")
        _insert_points(tx, panel, 0, "derived")
    return len(panel)


def load_panel(synthetic=False):
    """The stored feed as a panel. Where sources overlap, simulated beats ingest beats derived."""
    s = db.store()
    q = "SELECT region, month, signal, category, value, synthetic, source FROM signal_points"
    q += "" if synthetic else " WHERE synthetic = 0"
    df = s.df(q)
    if df.empty and not s.scalar("SELECT COUNT(*) AS n FROM signal_points"):
        materialize()
        df = s.df(q)
    df["value"] = df["value"].astype(float)
    df["_rank"] = df["source"].map(_SOURCE_RANK).fillna(0)
    df = df.sort_values("_rank", kind="stable").drop_duplicates(["region", "month", "signal"], keep="last")
    return df.drop(columns="_rank").reset_index(drop=True)


def run_detection():
    """Detect on the stored feed (derived + ingested) and replace the real alerts."""
    return save(group(detect(load_panel())))


def run():
    """Full rebuild: re-derive the feed from source tables, then detect."""
    materialize()
    return run_detection()


def feed_summary():
    rows = db.store().query(
        "SELECT source, COUNT(*) AS n, MIN(month) AS first, MAX(month) AS last FROM signal_points GROUP BY source")
    return {r["source"]: {"points": int(r["n"]), "first": r["first"], "last": r["last"]} for r in rows}


def ingest(points):
    """Live-feed ingestion. points: [{region, month 'YYYY-MM', signal, value, category?}].

    Validated strictly, stored as source 'ingest', then detection reruns so alerts reflect the new data.
    """
    regions = set(db.region_systems())
    cats = set(db.complaints()["category"].unique())
    clean = []
    for i, p in enumerate(points):
        region, month, signal = p.get("region"), str(p.get("month", "")), p.get("signal", "")
        try:
            value = float(p.get("value"))
        except (TypeError, ValueError):
            raise ValueError(f"point {i}: value must be a number")
        if region not in regions:
            raise ValueError(f"point {i}: unknown region {region!r}")
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
            raise ValueError(f"point {i}: month must be YYYY-MM")
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"point {i}: value must be finite and >= 0")
        category = None
        if signal.startswith("complaints:"):
            category = signal.split(":", 1)[1]
            if category not in cats:
                raise ValueError(f"point {i}: unknown category {category!r}")
        elif signal not in (*METER_SIGNALS, "sla_breach_rate"):
            raise ValueError(f"point {i}: unknown signal {signal!r}")
        clean.append({"region": region, "month": month, "signal": signal, "category": category, "value": value})
    if not clean:
        raise ValueError("no points")
    with db.store().transaction() as tx:
        for r in clean:
            tx.execute("DELETE FROM signal_points WHERE source = 'ingest' AND region = ? AND month = ? AND signal = ?",
                       (r["region"], r["month"], r["signal"]))
        _insert_points(tx, pd.DataFrame(clean), 0, "ingest")
    alerts = run_detection()
    return {"ingested": len(clean), "active_alerts": [a for a in alerts if a["status"] == "active"]}


def clear_ingested():
    db.store().execute("DELETE FROM signal_points WHERE source = 'ingest'")
    return run_detection()


# ---- Simulated feed for the demo -------------------------------------------------------------

SCENARIO_MONTH = "2026-10"
SCENARIO = {
    "name": "MeterHub estimation fault",
    "description": "Simulated October update: MeterHub pushes a bad estimation batch. "
                   "Barrowdale and Dunmoor see estimated-read complaints and billing exceptions jump.",
    "regions": ["Barrowdale", "Dunmoor"],
    "complaint_multiplier": {"Billing - estimated read": 2.6, "Billing - disputed amount": 1.5},
    "exceptions_multiplier": 1.45,
    "estimated_read_delta": 0.12,
}


def inject_scenario():
    """Write a synthetic month into the stored feed, then run the same detector over the stored data."""
    panel = load_panel()
    last = panel[panel["month"] == panel[panel["signal"].str.startswith("complaints:")]["month"].max()]
    last_meter = panel[panel["month"] == "2026-09"]
    new = pd.concat([last, last_meter[last_meter["signal"].isin(METER_SIGNALS)]])
    new = new[new["signal"] != "sla_breach_rate"].drop_duplicates(["region", "signal"]).copy()
    new["month"] = SCENARIO_MONTH
    hit = new["region"].isin(SCENARIO["regions"])
    for cat, mult in SCENARIO["complaint_multiplier"].items():
        rows = hit & (new["signal"] == f"complaints:{cat}")
        new.loc[rows, "value"] = (new.loc[rows, "value"] * mult).round()
    new.loc[hit & (new["signal"] == "exceptions_per_1k"), "value"] *= SCENARIO["exceptions_multiplier"]
    new.loc[hit & (new["signal"] == "estimated_read_rate"), "value"] += SCENARIO["estimated_read_delta"]
    reset_scenario()
    with db.store().transaction() as tx:
        _insert_points(tx, new, 1, "simulated")
    alerts = group(detect(load_panel(synthetic=True), months={SCENARIO_MONTH}), synthetic=True)
    return save(alerts, replace_real=False)


def reset_scenario():
    with db.store().transaction() as tx:
        tx.execute("DELETE FROM alerts WHERE synthetic = 1")
        tx.execute("DELETE FROM signal_points WHERE synthetic = 1")


def load_alerts(status=None):
    q = "SELECT * FROM alerts" + (" WHERE status = ?" if status else "") + " ORDER BY month DESC, z DESC"
    rows = db.store().query(q, (status,) if status else ())
    for d in rows:
        for k in ("regions", "shared_systems", "detail"):
            d[k] = json.loads(d[k])
    return rows


if __name__ == "__main__":
    alerts = run()
    print(f"{len(alerts)} alerts")
    for a in alerts:
        print(a["status"][:4], a["month"], f"z={a['z']:5.2f}", a["detail"]["summary"])
