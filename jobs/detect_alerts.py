"""Early-warning alerts (#3): spot unusual signals per region, then connect the dots.

Run:  python -m jobs.detect_alerts

Signals per region and month: complaint count per category, SLA breach rate, billing exceptions
per 1k accounts, estimated read rate. A signal fires when its z-score against the region's own
trailing 6 months is >= 3 (spikes) or when a CUSUM detector crosses its threshold (slow drift).
Alerts on the same signal in the same month in 2+ regions are grouped and tagged with the
systems those regions share.
"""

import json

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
        alert_id = f"{'SIM' if synthetic else 'AL'}-{month}-{abs(hash((signal, tuple(regions)))) % 10**6:06d}"
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


def save(alerts, replace_real=True, conn=None):
    conn = conn or db.app_conn()
    with conn:
        if replace_real:
            conn.execute("DELETE FROM alerts WHERE synthetic = 0")
        conn.executemany(
            "INSERT OR REPLACE INTO alerts VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(a["alert_id"], a["month"], a["signal"], a["category"], json.dumps(a["regions"]),
              a["z"], json.dumps(a["shared_systems"]), a["status"], a["synthetic"],
              json.dumps(a["detail"])) for a in alerts],
        )
    return alerts


def run():
    return save(group(detect(build_panel())))


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
    """Append a synthetic month to the real panel, run the same detector on it, store results."""
    panel = build_panel()
    last = panel[panel["month"] == panel[panel["signal"].str.startswith("complaints:")]["month"].max()]
    last_meter = panel[panel["month"] == "2026-09"]
    new = pd.concat([last, last_meter[last_meter["signal"].isin(METER_SIGNALS)]]).drop_duplicates()
    new = new[new["signal"] != "sla_breach_rate"].copy()
    new["month"] = SCENARIO_MONTH
    hit = new["region"].isin(SCENARIO["regions"])
    for cat, mult in SCENARIO["complaint_multiplier"].items():
        rows = hit & (new["signal"] == f"complaints:{cat}")
        new.loc[rows, "value"] = (new.loc[rows, "value"] * mult).round()
    new.loc[hit & (new["signal"] == "exceptions_per_1k"), "value"] *= SCENARIO["exceptions_multiplier"]
    new.loc[hit & (new["signal"] == "estimated_read_rate"), "value"] += SCENARIO["estimated_read_delta"]
    alerts = group(detect(pd.concat([panel, new]), months={SCENARIO_MONTH}), synthetic=True)
    reset_scenario()
    return save(alerts, replace_real=False)


def reset_scenario():
    conn = db.app_conn()
    with conn:
        conn.execute("DELETE FROM alerts WHERE synthetic = 1")


def load_alerts(status=None):
    conn = db.app_conn()
    q = "SELECT * FROM alerts" + (" WHERE status = ?" if status else "") + " ORDER BY month DESC, z DESC"
    rows = conn.execute(q, (status,) if status else ()).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("regions", "shared_systems", "detail"):
            d[k] = json.loads(d[k])
        out.append(d)
    return out


if __name__ == "__main__":
    alerts = run()
    print(f"{len(alerts)} alerts")
    for a in alerts:
        print(a["status"][:4], a["month"], f"z={a['z']:5.2f}", a["detail"]["summary"])
