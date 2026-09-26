"""Backlog planner defaults (#2). The projection itself runs client-side from these numbers.

Throughput per agent = recent closures / assumed headcount. The headcount is an assumption we
set and show. Router effect: handling effort scales with the Finance cost model (GBP 121 for a
transferred complaint vs GBP 68), so fewer transfers means more closures per agent.
"""

from engine import cost_model, db, queue, queue_score


def defaults():
    k = db.monthly_kpis()
    recent = k.tail(3)
    c = db.complaints()
    closed = c[~c["is_open"]]
    recent_closed = closed[closed["date_closed"].dt.strftime("%Y-%m") >= recent["month"].min()]
    fte = queue_score.config()["assumed_complaint_fte"]
    closures = float(recent["complaints_closed"].mean())
    backlog = int(len(queue.open_cases(include_auto=True)))
    return {
        "as_of": str(db.AS_OF),
        "backlog": backlog,
        "inflow": round(float(recent["complaints_opened"].mean())),
        "closures": round(closures),
        "assumed_fte": fte,
        "per_agent": round(closures / fte, 2),
        "fte_cost": cost_model.cost("agent_fte"),
        "transfer_share": round(float(recent_closed["transferred_between_systems"].mean()), 3),
        "cost": {"not": cost_model.cost("complaint"), "transferred": cost_model.cost("complaint_transferred")},
        "router_defaults": {"adoption": 0.8, "avoidance": 0.6},
    }
