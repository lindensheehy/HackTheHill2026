"""Northwind Complaint Triage API.

Run:  python -m uvicorn api.main:app --port 8000
If web/dist exists (npm run build), the front end is served from / as well.
Every endpoint declares the permission it needs (api/auth.py); with auth off, everyone is a local admin.
"""

import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from api.auth import current_user, public_config, require
from engine import assistant, build_baselines, config, dashboard, db, planner, queue, replay, router, store, usage, voice
from jobs import detect_alerts

app = FastAPI(title="Northwind Complaint Triage")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

READ = Depends(require("read"))


@app.on_event("startup")
def _startup():
    build_baselines.load()
    if not detect_alerts.load_alerts():
        detect_alerts.run()
    _static_dashboard()
    if config.DETECT_INTERVAL_MINUTES > 0:
        threading.Thread(target=_scheduler, daemon=True, name="detect-alerts").start()


def _scheduler():
    """Rerun detection on the stored feed so ingested points turn into alerts without a manual step."""
    while True:
        time.sleep(config.DETECT_INTERVAL_MINUTES * 60)
        try:
            detect_alerts.run_detection()
        except Exception as e:  # keep the loop alive; the next run may succeed
            print("scheduled detection failed:", e)


def _errors(fn):
    try:
        return fn()
    except usage.BudgetExceeded as e:
        raise HTTPException(429, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))


# ---- Config / identity -----------------------------------------------------------------------

@app.get("/api/config")
def get_config():
    """Public: the SPA needs it before login. No secrets."""
    return {"as_of": str(db.AS_OF), "auth": public_config(), "store": store.info(),
            "ai": {"gemini": assistant.gemini_enabled(), "model": config.GEMINI_MODEL if assistant.gemini_enabled() else None},
            "voice": voice.status()}


@app.get("/api/me")
def me(user=Depends(current_user)):
    return user


@app.get("/api/usage", dependencies=[READ])
def get_usage():
    return usage.summary()


# ---- Reference -------------------------------------------------------------------------------

@app.get("/api/meta", dependencies=[READ])
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
def triage(intake: Intake, create: bool = True, user=Depends(current_user)):
    """Route a complaint. With create=true (default) it is also added to the queue."""
    if intake.priority not in router.SLA_DAYS:
        raise HTTPException(400, "priority must be P1, P2 or P3")
    need = "intake:create" if create else "read"
    if need not in user["permissions"]:
        raise HTTPException(403, f"your role ({user['role']}) can't do this: needs '{need}'")
    data = intake.model_dump() if hasattr(intake, "model_dump") else intake.dict()
    return queue.create_intake(data) if create else router.route_live(data)


@lru_cache(maxsize=1)
def _replay():
    return replay.replay()


@app.get("/api/replay", dependencies=[READ])
@app.post("/api/replay", dependencies=[READ])
def replay_data():
    return _replay()


# ---- #2 Queue --------------------------------------------------------------------------------

@app.get("/api/queue", dependencies=[READ])
def get_queue(strict: bool = False, region: str = "", category: str = "", priority: str = "",
              owner: str = "", system: str = "", search: str = "",
              limit: int = Query(100, le=2000), offset: int = 0):
    filters = {"region": region, "category": category, "priority": priority, "owner": owner,
               "system": system, "search": search}
    return queue.queue(strict=strict, filters=filters, limit=limit, offset=offset)


@app.get("/api/queue/auto", dependencies=[READ])
def get_auto_lane():
    return queue.auto_lane()


@app.get("/api/cases/{complaint_id}", dependencies=[READ])
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
def post_event(complaint_id: str, event: Event, user=Depends(current_user)):
    need = "cases:assign" if event.type == "assign" else "cases:write"
    if need not in user["permissions"]:
        raise HTTPException(403, f"your role ({user['role']}) can't do this: needs '{need}'")
    note = event.note
    if user.get("auth") and event.type in ("note", "status", "assign"):
        note = f"{note or ''} (by {user['name']})".strip()
    try:
        queue.add_event(complaint_id, event.type, event.value, note)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return queue.case_detail(complaint_id)


@app.get("/api/planner", dependencies=[READ])
def get_planner():
    return planner.defaults()


# ---- Voice (ElevenLabs, optional) -------------------------------------------------------------

def _case_or_404(complaint_id):
    d = queue.case_detail(complaint_id)
    if d is None or d["case"].get("closed"):
        raise HTTPException(404, "no such open complaint")
    return d


@app.get("/api/cases/{complaint_id}/customer-update", dependencies=[READ])
def customer_update(complaint_id: str):
    d = _case_or_404(complaint_id)
    return {"text": voice.case_update_text(d), "provider": "elevenlabs" if voice.elevenlabs_enabled() else "browser"}


@app.get("/api/cases/{complaint_id}/customer-update/audio", dependencies=[Depends(require("assistant:use"))])
def customer_update_audio(complaint_id: str):
    """Server-side text only, so this endpoint can't be used to synthesise arbitrary text."""
    text = voice.case_update_text(_case_or_404(complaint_id))
    audio, cached = _errors(lambda: voice.synthesize(text))
    return Response(audio, media_type="audio/mpeg", headers={"X-Cache": "hit" if cached else "miss"})


class Speak(BaseModel):
    text: str


@app.post("/api/voice/tts", dependencies=[Depends(require("assistant:use"))])
def tts(body: Speak):
    audio, cached = _errors(lambda: voice.synthesize(body.text))
    return Response(audio, media_type="audio/mpeg", headers={"X-Cache": "hit" if cached else "miss"})


# ---- Assistant (Gemini, optional) -------------------------------------------------------------

class Turn(BaseModel):
    role: str
    text: str


class Ask(BaseModel):
    question: str
    history: List[Turn] = []
    case_id: Optional[str] = None
    alert_id: Optional[str] = None
    page: Optional[str] = None


@app.post("/api/assistant/ask", dependencies=[Depends(require("assistant:use"))])
def ask(body: Ask):
    hist = [t.model_dump() if hasattr(t, "model_dump") else t.dict() for t in body.history]
    return _errors(lambda: assistant.ask(body.question, hist, body.case_id, body.alert_id, body.page))


@app.post("/api/assistant/brief/{alert_id}", dependencies=[Depends(require("assistant:use"))])
def alert_brief(alert_id: str, force: bool = False):
    b = _errors(lambda: assistant.brief(alert_id, force=force))
    if b is None:
        raise HTTPException(404, "no such alert")
    return b


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


@app.get("/api/dashboard", dependencies=[READ])
def get_dashboard():
    return _static_dashboard()


@app.get("/api/graph", dependencies=[READ])
def get_graph():
    return dashboard.graph(detect_alerts.load_alerts(status="active"))


@app.get("/api/alerts", dependencies=[READ])
def get_alerts(status: Optional[str] = None):
    return {"alerts": detect_alerts.load_alerts(status), "scenario": detect_alerts.SCENARIO,
            "feed": detect_alerts.feed_summary(), "store": store.info()}


@app.get("/api/alerts/{alert_id}", dependencies=[READ])
def get_alert(alert_id: str):
    a = next((a for a in detect_alerts.load_alerts() if a["alert_id"] == alert_id), None)
    if a is None:
        raise HTTPException(404, "no such alert")
    panel = detect_alerts.load_panel(synthetic=bool(a["synthetic"]))
    series = {}
    for region in a["regions"]:
        s = panel[(panel["region"] == region) & (panel["signal"] == a["signal"])].sort_values("month")
        series[region] = [{"month": m, "v": round(float(v), 4), "simulated": bool(syn), "source": src}
                          for m, v, syn, src in zip(s["month"], s["value"], s["synthetic"], s["source"])]
    cats = a["detail"].get("related_categories", [])
    open_q = queue.open_cases(include_auto=True)
    linked = open_q[open_q["region"].isin(a["regions"]) & open_q["category"].isin(cats)]
    linked = linked.sort_values("queue_score", ascending=False)
    return {"alert": a, "series": series, "linked_open": queue.rows(linked.head(50)),
            "linked_open_total": int(len(linked))}


@app.post("/api/alerts/inject", dependencies=[Depends(require("alerts:simulate"))])
def inject():
    return {"alerts": detect_alerts.inject_scenario(), "scenario": detect_alerts.SCENARIO}


@app.post("/api/alerts/reset", dependencies=[Depends(require("alerts:simulate"))])
def reset_alerts():
    detect_alerts.reset_scenario()
    return {"ok": True}


# ---- Live signal feed (Tiger Data time series) ------------------------------------------------

class Point(BaseModel):
    region: str
    month: str
    signal: str
    value: float


@app.get("/api/signals", dependencies=[READ])
def get_signals():
    return {"feed": detect_alerts.feed_summary(), "store": store.info()}


@app.post("/api/signals", dependencies=[Depends(require("signals:write"))])
def post_signals(points: List[Point]):
    rows = [p.model_dump() if hasattr(p, "model_dump") else p.dict() for p in points]
    return _errors(lambda: detect_alerts.ingest(rows))


@app.delete("/api/signals", dependencies=[Depends(require("signals:write"))])
def delete_signals():
    detect_alerts.clear_ingested()
    return {"ok": True}


@app.post("/api/demo/reset", dependencies=[Depends(require("demo:reset"))])
def reset_demo():
    queue.reset_demo()
    return {"ok": True}


# ---- Static front end --------------------------------------------------------------------------

DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "no such endpoint")
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")
