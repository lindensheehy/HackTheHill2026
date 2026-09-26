"""Single source of truth for unit costs and the per-transfer penalty."""

from functools import lru_cache

from engine import db

_ITEMS = {
    "call": "Inbound call handled by agent",
    "complaint": "Complaint handled end to end (average)",
    "complaint_transferred": "Complaint handled end to end (transferred between systems)",
    "bill_correction": "Manual bill correction and re-issue",
    "field_visit": "Field meter visit",
    "smart_meter": "Smart meter installation",
    "agent_fte": "Contact centre agent, fully loaded",
    "ai_pilot": "AskNorthwind assistant pilot",
    "regulator_penalty_quarter": "Regulator penalty, enhanced monitoring",
    "compensation": "Compensation payment, missed appointment or outage",
}


@lru_cache(maxsize=None)
def costs():
    uc = db.unit_costs().set_index("item")
    return {key: float(uc.loc[item, "unit_cost"]) for key, item in _ITEMS.items()}


def cost(key):
    return costs()[key]


@lru_cache(maxsize=None)
def transfer_penalty():
    """Average difference between a transferred and a non-transferred closed complaint."""
    cl = db.closed_complaints()
    g = cl.groupby("transferred_between_systems")
    t, n = g.get_group(1), g.get_group(0)
    return {
        "transfer_share": float(cl["transferred_between_systems"].mean()),
        "days": {"transferred": float(t.days_to_close.mean()), "not": float(n.days_to_close.mean())},
        "breach": {"transferred": float(t.sla_breach.mean()), "not": float(n.sla_breach.mean())},
        "reopen": {"transferred": float(t.reopened.mean()), "not": float(n.reopened.mean())},
        "cost": {"transferred": cost("complaint_transferred"), "not": cost("complaint")},
        "per_avoided": {
            "gbp": cost("complaint_transferred") - cost("complaint"),
            "days": float(t.days_to_close.mean() - n.days_to_close.mean()),
            "reopens": float(t.reopened.mean() - n.reopened.mean()),
            "breaches": float(t.sla_breach.mean() - n.sla_breach.mean()),
        },
    }


def expected_cost(transfer_risk):
    return transfer_risk * cost("complaint_transferred") + (1 - transfer_risk) * cost("complaint")
