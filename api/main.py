"""Northwind Complaint Triage API.

Run:  uvicorn api.main:app --reload --port 8000
If web/dist exists (npm run build), the front end is served from / as well.
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from engine import build_baselines, dashboard, db, planner, queue, replay, router
from jobs import detect_alerts

app = FastAPI(title="Northwind Complaint Triage")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _startup():
    build_baselines.load()
    if not detect_alerts.load_alerts():
        detect_alerts.run()
    _static_dashboard()


# ---- Reference -------------------------------------------------------------------------------

@app.get("/api/meta")
def meta():
    c = db.complaints()
    return {
        "as_of": str(db.AS_OF),
        "channels": sorted(c["channel"].unique()),
        "categories": sorted(c["category"].unique()),
        "regions": sorted(c["region"].unique()),
        "priorities": ["P1", "P2", "P3"],
        "sla_days": router.SLA_DAYS,
        "teams": sorted(set(router.TEAMS.values())),
        "entry_systems": [{"id": s, "name": router.SYSTEM_NAMES[s]} for s in ("SYS-01", "SYS-03", "SYS-04", "SYS-05")],
        "channel_entry": router.CHANNEL_ENTRY,
        "examples": EXAMPLES,
    }


EXAMPLES = [
    {"title": "Barrowdale estimated read", "blurb": "No smart meters, 62% estimated reads; picks up any live alert.",
     "intake": {"channel": "Phone", "category": "Billing - estimated read", "priority": "P2",
                "region": "Barrowdale", "account_id": "ACC-980200", "entry_system": "SYS-05"}},
    {"title": "Disputed bill via web", "blurb": "Arrives in self-service: 46% chance of a transfer today.",
     "intake": {"channel": "Web form", "category": "Billing - disputed amount", "priority": "P3",
                "region": "Fenwick", "account_id": "ACC-730009", "entry_system": "SYS-03"}},
    {"title": "Poor communication by email", "blurb": "53% information-only: goes to the auto-answer lane.",
     "intake": {"channel": "Email", "category": "Service - poor communication", "priority": "P3",
                "region": "Ashford", "account_id": "ACC-615081", "entry_system": "SYS-05"}},
    {"title": "Regulator referral, supply outage", "blurb": "P1 with a 5-day SLA: jumps ahead of every case that is less urgent.",
     "intake": {"channel": "Regulator referral", "category": "Supply - interruption", "priority": "P1",
                "region": "Dunmoor", "account_id": "ACC-489331", "entry_system": "SYS-05"}},
]


# ---- #1 Routing ------------------------------------------------------------------------------

class Intake(BaseModel):
    channel: str
    category: str
    priority: str
    region: str
    account_id: Optional[str] = None
    entry_system: Optional[str] = None


@app.post("/api/triage")
def triage(intake: Intake, create: bool = True):
    """Route a complaint. With create=true (default) it is also added to the queue."""
    if intake.priority not in router.SLA_DAYS:
        raise HTTPException(400, "priority must be P1, P2 or P3")
    data = intake.model_dump() if hasattr(intake, "model_dump") else intake.dict()
    return queue.create_intake(data) if create else router.route_live(data)


@lru_cache(maxsize=1)
def _replay():
    return replay.replay()


@app.get("/api/replay")
@app.post("/api/replay")
def replay_data():
    return _replay()


# ---- #2 Queue --------------------------------------------------------------------------------

@app.get("/api/queue")
def get_queue(strict: bool = False, region: str = "", category: str = "", priority: str = "",
              owner: str = "", system: str = "", search: str = "",
              limit: int = Query(100, le=2000), offset: int = 0):
    filters = {"region": region, "category": category, "priority": priority, "owner": owner,
               "system": system, "search": search}
    return queue.queue(strict=strict, filters=filters, limit=limit, offset=offset)


@app.get("/api/queue/auto")
def get_auto_lane():
    return queue.auto_lane()


@app.get("/api/cases/{complaint_id}")
def get_case(complaint_id: str):
    d = queue.case_detail(complaint_id)
    if d is None:
        raise HTTPException(404, "no such complaint")
    return d


class Event(BaseModel):
    type: str
    value: Optional[str] = None
    note: Optional[str] = None


@app.post("/api/cases/{complaint_id}/events")
def post_event(complaint_id: str, event: Event):
    try:
        queue.add_event(complaint_id, event.type, event.value, event.note)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return queue.case_detail(complaint_id)


@app.get("/api/planner")
def get_planner():
    return planner.defaults()


# ---- #3 Dashboard ----------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _static_dashboard():
    return {
        "kpis": dashboard.kpi_header(),
        "monthly": dashboard.monthly(),
        "transfer": dashboard.transfer_panel(),
        "regions": dashboard.regions(),
        "heatmap": dashboard.heatmap(),
        "smart_meter": dashboard.smart_meter(),
        "talking_points": dashboard.talking_points(),
    }


@app.get("/api/dashboard")
def get_dashboard():
    return _static_dashboard()


@app.get("/api/graph")
def get_graph():
    return dashboard.graph(detect_alerts.load_alerts(status="active"))


@app.get("/api/alerts")
def get_alerts(status: Optional[str] = None):
    return {"alerts": detect_alerts.load_alerts(status), "scenario": detect_alerts.SCENARIO}


@app.get("/api/alerts/{alert_id}")
def get_alert(alert_id: str):
    a = next((a for a in detect_alerts.load_alerts() if a["alert_id"] == alert_id), None)
    if a is None:
        raise HTTPException(404, "no such alert")
    panel = detect_alerts.build_panel()
    if a["synthetic"]:
        # Rebuild the synthetic month so the spike chart shows the injected point.
        pass
    series = {}
    for region in a["regions"]:
        s = panel[(panel["region"] == region) & (panel["signal"] == a["signal"])].sort_values("month")
        series[region] = [{"month": m, "v": round(float(v), 4)} for m, v in zip(s["month"], s["value"])]
        if a["synthetic"]:
            point = next((p for p in a["detail"]["per_region"] if p["region"] == region), None)
            if point:
                series[region].append({"month": a["month"], "v": point["value"], "simulated": True})
    cats = a["detail"].get("related_categories", [])
    open_q = queue.open_cases(include_auto=True)
    linked = open_q[open_q["region"].isin(a["regions"]) & open_q["category"].isin(cats)]
    linked = linked.sort_values("queue_score", ascending=False)
    return {"alert": a, "series": series, "linked_open": queue.rows(linked.head(50)),
            "linked_open_total": int(len(linked))}


@app.post("/api/alerts/inject")
def inject():
    return {"alerts": detect_alerts.inject_scenario(), "scenario": detect_alerts.SCENARIO}


@app.post("/api/alerts/reset")
def reset_alerts():
    detect_alerts.reset_scenario()
    return {"ok": True}


@app.post("/api/demo/reset")
def reset_demo():
    queue.reset_demo()
    return {"ok": True}


# ---- Static front end --------------------------------------------------------------------------

DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")
