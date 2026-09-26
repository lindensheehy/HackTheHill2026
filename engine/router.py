"""Intake Routing Engine (#1).

`route(intake, tables, context)` is a pure function: given what's known when a complaint
arrives, plus the precomputed baselines and a small context dict, it returns a TriageResult.
`route_live(intake)` gathers the baselines and context from the database for you.

Transfers can't be predicted from complaint attributes (they're flat at ~46% outside CaseTrack),
so the routing itself is a deterministic policy: create the case in CaseTrack at intake with
the owning team decided by category. The learned tables only describe what to expect.
"""

from engine import cost_model

CASE_SYSTEM = "SYS-04"  # CaseTrack: complaints that start here are never transferred

# Owner policy. The teams are ours to name; each owns a category's full set of resolution actions.
TEAMS = {
    "Billing - disputed amount": "Billing Resolution",
    "Billing - estimated read": "Billing Resolution",
    "Metering - no read taken": "Metering Operations",
    "Payment - plan or arrears": "Payments & Arrears",
    "Service - missed appointment": "Field Scheduling",
    "Service - poor communication": "Customer Relations",
    "Supply - interruption": "Network Operations",
    "Water - pressure or quality": "Water Operations",
    "Other": "Customer Relations",
}

# Systems the owning team needs alongside CaseTrack. Billing/metering depend on the region.
TEAM_SYSTEMS = {
    "Payments & Arrears": ["SYS-02"],
    "Field Scheduling": ["SYS-08"],
    "Customer Relations": ["SYS-14"],
    "Network Operations": ["SYS-09", "SYS-08"],
    "Water Operations": ["SYS-10", "SYS-08"],
}

SYSTEM_NAMES = {
    "SYS-01": "Aurora Billing", "SYS-02": "Helix CIS", "SYS-03": "Northwind Connect",
    "SYS-04": "CaseTrack", "SYS-05": "CallCentre One", "SYS-06": "MeterHub",
    "SYS-07": "SmartRead Gateway", "SYS-08": "FieldForce", "SYS-09": "GridWatch",
    "SYS-10": "AquaTrack", "SYS-14": "DocVault",
}

# Default entry system for each channel when the caller doesn't say where it arrived.
CHANNEL_ENTRY = {
    "Phone": "SYS-05", "Web form": "SYS-03", "Email": "SYS-05", "Social": "SYS-03",
    "Post": "SYS-05", "Regulator referral": "SYS-05",
}

SLA_DAYS = {"P1": 5, "P2": 10, "P3": 20}
INFO_ONLY_ACTION = "Information provided only"
BILLING_CATEGORIES = {"Billing - disputed amount", "Billing - estimated read", "Metering - no read taken"}


def sys_label(sid):
    return f"{sid} {SYSTEM_NAMES.get(sid, '')}".strip()


def _linked_systems(team, region_systems):
    if team in ("Billing Resolution", "Metering Operations"):
        # Barrowdale/Dunmoor bill on Aurora + MeterHub; the rest on Helix + SmartRead.
        return region_systems or ["SYS-02"]
    return TEAM_SYSTEMS.get(team, [])


def _lookup(table, *keys):
    """First key that exists, so (category, priority) falls back to (category, *)."""
    for k in keys:
        if k in table:
            return table[k]
    return None


def route(intake, tables, context=None):
    """Return the TriageResult dict for one intake. No I/O."""
    context = context or {}
    cat, pri, ch, region = intake["category"], intake["priority"], intake["channel"], intake["region"]
    entry = intake.get("entry_system") or CHANNEL_ENTRY.get(ch, "SYS-05")
    reasons = []

    # 1. Owner (policy)
    team = TEAMS.get(cat, "Customer Relations")
    region_info = tables["region_signals"].get(region, {})
    region_systems = region_info.get("systems", [])
    linked = _linked_systems(team, region_systems if cat in BILLING_CATEGORIES else [])
    reasons.append(f"Case created in CaseTrack at intake; '{cat}' is owned end to end by {team}")

    # Legacy route: what would have happened had it stayed with the entry system
    tr = tables["transfer_rate"].get(entry, {"rate": 0.0, "by_category": {}})
    transfer_risk = 0.0 if entry == CASE_SYSTEM else tr["rate"]
    if transfer_risk > 0:
        reasons.append(
            f"Complaints entering via {SYSTEM_NAMES.get(entry, entry)} are transferred "
            f"{transfer_risk:.0%} of the time, whatever their category"
        )
    else:
        reasons.append("Entered via CaseTrack, which never transfers: legacy and routed paths match")

    # 2. Resolution path (learned, non-transferred history)
    paths = _lookup(tables["resolution_path"], f"{cat}|{pri}", f"{cat}|*") or []
    resolution_path = [
        {k: p[k] for k in ("action", "share", "median_days", "reopen_rate")} for p in paths[:3]
    ]
    if resolution_path:
        top = resolution_path[0]
        reasons.append(f"Most likely outcome: {top['action']} ({top['share']:.0%} of similar cases)")

    # 3. Info-only likelihood (smoothed by channel)
    io = _lookup(tables["info_only"], f"{cat}|{ch}", f"{cat}|*") or {"rate": 0.0}
    info_only_likelihood = io["rate"]
    if info_only_likelihood >= 0.4:
        reasons.append(f"{info_only_likelihood:.0%} of similar complaints needed information only: auto-answer candidate")

    # 4. Expected days / breach risk: routed = non-transferred history, legacy = blend by transfer risk
    o_not = _lookup(tables["outcomes"], f"{cat}|{pri}|0", f"{cat}|*|0")
    o_tr = _lookup(tables["outcomes"], f"{cat}|{pri}|1", f"{cat}|*|1") or o_not

    def blend(key):
        return transfer_risk * o_tr[key] + (1 - transfer_risk) * o_not[key]

    expected_days = {"routed": round(o_not["mean_days"], 1), "legacy": round(blend("mean_days"), 1)}
    breach_risk = {"routed": round(o_not["breach"], 3), "legacy": round(blend("breach"), 3)}
    reopen_risk = {"routed": round(o_not["reopen"], 3), "legacy": round(blend("reopen"), 3)}
    cost = {"routed": cost_model.cost("complaint"), "legacy": round(cost_model.expected_cost(transfer_risk), 2)}
    if transfer_risk > 0:
        reasons.append(
            f"Routing at intake saves ~{expected_days['legacy'] - expected_days['routed']:.1f} days "
            f"and ~£{cost['legacy'] - cost['routed']:.0f} on average for this category and priority"
        )

    # 5. Context
    alert = context.get("region_alert")
    prior = context.get("account_prior_complaints", 0)
    if alert:
        reasons.append(f"Active alert: {alert['summary']}")
    if prior:
        reasons.append(f"Account has {prior} earlier complaint{'s' if prior != 1 else ''}; history attached")
    if region_info and region_info.get("smart_meter_penetration", 1) == 0 and cat in BILLING_CATEGORIES:
        reasons.append(
            f"{region} has no smart meters and {region_info['estimated_read_rate']:.0%} estimated reads"
        )

    return {
        "complaint_id": intake.get("complaint_id"),
        "intake": {"channel": ch, "category": cat, "priority": pri, "region": region,
                   "account_id": intake.get("account_id"), "sla_days": SLA_DAYS.get(pri)},
        "owner": {"system": sys_label(CASE_SYSTEM), "team": team,
                  "linked_systems": [sys_label(s) for s in linked]},
        "legacy_route": {"entry_system": sys_label(entry), "transfer_risk": round(transfer_risk, 3)},
        "resolution_path": resolution_path,
        "info_only_likelihood": round(info_only_likelihood, 3),
        "expected_days": expected_days,
        "breach_risk": breach_risk,
        "reopen_risk": reopen_risk,
        "cost": cost,
        "context": {
            "region_alert": alert["summary"] if alert else None,
            "region_alert_id": alert["alert_id"] if alert else None,
            "region_systems": [sys_label(s) for s in region_systems],
            "region_signals": {k: region_info.get(k) for k in
                               ("estimated_read_rate", "smart_meter_penetration", "exceptions_per_1k")},
            "account_prior_complaints": prior,
        },
        "queue_score": 0.0,
        "reasons": reasons,
    }


def route_live(intake):
    """route() with baselines and context loaded from the database."""
    from engine import build_baselines, context as ctx
    return route(intake, build_baselines.load(), ctx.gather(intake))
