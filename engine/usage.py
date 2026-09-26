"""Daily usage counters for paid services. Hard caps live here, so a runaway loop or an abusive client can't
burn credits. Day = wall-clock UTC date (budgets are about real spend, not the data's as-of date)."""

from datetime import datetime, timezone

from engine import config, db

LIMITS = {
    # service: (unit name, daily cap)
    "gemini": ("calls", lambda: config.GEMINI_MAX_CALLS_PER_DAY),
    "elevenlabs": ("chars", lambda: config.ELEVENLABS_MAX_CHARS_PER_DAY),
}


class BudgetExceeded(RuntimeError):
    pass


def _today():
    return datetime.now(timezone.utc).date().isoformat()


def used(service):
    rows = db.store().query("SELECT units, calls FROM usage WHERE day = ? AND service = ?", (_today(), service))
    return {"units": float(rows[0]["units"]), "calls": int(rows[0]["calls"])} if rows else {"units": 0.0, "calls": 0}


def check(service, units):
    """Raise BudgetExceeded if spending `units` now would pass today's cap."""
    unit, cap = LIMITS[service]
    u = used(service)
    spent = u["calls"] if unit == "calls" else u["units"]
    if spent + units > cap():
        raise BudgetExceeded(f"{service} daily cap reached ({cap()} {unit}/day)")


def add(service, units, calls=1):
    day = _today()
    with db.store().transaction() as tx:
        rows = tx.query("SELECT units, calls FROM usage WHERE day = ? AND service = ?", (day, service))
        if rows:
            tx.execute("UPDATE usage SET units = ?, calls = ? WHERE day = ? AND service = ?",
                       (float(rows[0]["units"]) + units, int(rows[0]["calls"]) + calls, day, service))
        else:
            tx.execute("INSERT INTO usage (day, service, units, calls) VALUES (?,?,?,?)", (day, service, units, calls))


def summary():
    out = {}
    for service, (unit, cap) in LIMITS.items():
        u = used(service)
        out[service] = {"unit": unit, "cap": cap(), "used": u["calls"] if unit == "calls" else u["units"],
                        "calls": u["calls"], "tokens_or_chars": u["units"]}
    return out
