"""Sponsor integrations with every external service mocked. Runs against a temporary SQLite store so real
usage counters, caches and demo state are never touched."""

import io
import json
import time
import urllib.error

import pytest

from engine import assistant, build_baselines, config, queue, store, usage, voice
from jobs import detect_alerts


@pytest.fixture(scope="module", autouse=True)
def temp_store(tmp_path_factory):
    prev = store.use(store.SqliteStore(tmp_path_factory.mktemp("store") / "app.db"))
    build_baselines.load.cache_clear()
    build_baselines.build()
    detect_alerts.run()
    yield
    store.use(prev)
    build_baselines.load.cache_clear()


@pytest.fixture
def gemini(monkeypatch):
    """Fake Gemini: returns whatever the test puts in `reply`, and records requests."""
    state = {"reply": "", "calls": []}
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")

    def fake_post(body):
        state["calls"].append(body)
        return {"candidates": [{"content": {"parts": [{"text": state["reply"]}]}}],
                "usageMetadata": {"totalTokenCount": 1234}}
    monkeypatch.setattr(assistant, "_post_gemini", fake_post)
    return state


# ---- Assistant ------------------------------------------------------------------------------

def test_offline_answer_cites_real_evidence(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    r = assistant.ask("How much longer do transferred complaints take?")
    assert r["mode"] == "offline" and r["evidence"]
    assert all(e["id"].startswith("E") for e in r["evidence"])


def test_gemini_answer_keeps_valid_citations_only(gemini):
    gemini["reply"] = "Transferred complaints take 15 days longer [E2]; see also [E99]."
    r = assistant.ask("transfers?", page="dashboard")
    assert r["mode"] == "gemini"
    assert "[E2]" in r["answer"] and "[E99]" not in r["answer"]
    assert [e["id"] for e in r["evidence"]] == ["E2"]
    body = gemini["calls"][0]
    assert body["generationConfig"]["maxOutputTokens"] == config.GEMINI_MAX_OUTPUT_TOKENS
    assert "Evidence:" in body["systemInstruction"]["parts"][0]["text"]
    assert usage.used("gemini")["calls"] >= 1


def test_gemini_budget_cap_falls_back_offline(gemini, monkeypatch):
    monkeypatch.setattr(config, "GEMINI_MAX_CALLS_PER_DAY", 0)
    r = assistant.ask("transfers?")
    assert r["mode"] == "offline" and "cap" in r["note"]
    assert not gemini["calls"]


def test_gemini_failure_never_breaks_the_app(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")

    def boom(body):
        raise urllib.error.URLError("offline")
    monkeypatch.setattr(assistant, "_post_gemini", boom)
    r = assistant.ask("transfers?")
    assert r["mode"] == "offline" and "unavailable" in r["note"]


def test_case_context_is_in_the_evidence(gemini):
    gemini["reply"] = "Start with the bill [C2]."
    r = assistant.ask("what next?", case_id="NW-124358")
    assert r["evidence"][0]["id"] == "C2"
    assert "NW-124358" in gemini["calls"][0]["systemInstruction"]["parts"][0]["text"]


def test_brief_template_then_gemini_drops_uncited_and_caches(gemini, monkeypatch):
    alerts = detect_alerts.inject_scenario()
    try:
        aid = max(alerts, key=lambda a: a["z"])["alert_id"]
        monkeypatch.setattr(config, "GEMINI_API_KEY", "")
        t = assistant.brief(aid)
        assert t["mode"] == "template" and t["what_changed"] and t["check_next"]
        assert all(b["cites"] for sec in ("what_changed", "possible_explanations", "check_next") for b in t[sec])

        monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
        gemini["reply"] = json.dumps({
            "what_changed": [{"text": "Estimated-read complaints tripled in Barrowdale.", "cites": ["A2"]},
                             {"text": "Uncited claim.", "cites": []}],
            "possible_explanations": [{"text": "Possibly a MeterHub batch fault.", "cites": ["A5", "Z9"]}],
            "check_next": [{"text": "Check MeterHub batch logs.", "cites": ["A5"]}]})
        b = assistant.brief(aid)
        assert b["mode"] == "gemini" and not b["cached"]
        assert [x["text"] for x in b["what_changed"]] == ["Estimated-read complaints tripled in Barrowdale."]
        assert b["possible_explanations"][0]["cites"] == ["A5"]
        n = len(gemini["calls"])
        again = assistant.brief(aid)
        assert again["cached"] and len(gemini["calls"]) == n      # cached: no second model call
    finally:
        detect_alerts.reset_scenario()


# ---- Voice ----------------------------------------------------------------------------------

def test_update_text_follows_case_state_and_never_claims_resolution():
    d = queue.case_detail("NW-124358")
    t = voice.case_update_text(d)
    assert "resolved" not in t.lower() and "prioritised" in t        # overdue case
    queue.add_event("NW-124358", "status", "escalated")
    try:
        assert "senior member" in voice.case_update_text(queue.case_detail("NW-124358"))
    finally:
        store.get().execute("DELETE FROM case_events WHERE complaint_id = 'NW-124358'")


def test_elevenlabs_synthesis_is_cached_and_capped(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(voice, "CACHE_DIR", tmp_path)
    calls = []

    def fake_urlopen(req, timeout=0):
        calls.append(json.loads(req.data))
        return io.BytesIO(b"ID3fake-mp3")
    monkeypatch.setattr(voice.urllib.request, "urlopen", fake_urlopen)
    audio, cached = voice.synthesize("Hello there.")
    assert audio == b"ID3fake-mp3" and not cached
    assert calls[0]["model_id"] == config.ELEVENLABS_MODEL
    audio, cached = voice.synthesize("Hello   there.")            # same text after whitespace normalisation
    assert cached and len(calls) == 1
    with pytest.raises(ValueError):
        voice.synthesize("x" * (config.ELEVENLABS_MAX_CHARS_PER_REQUEST + 1))
    monkeypatch.setattr(config, "ELEVENLABS_MAX_CHARS_PER_DAY", 5)
    with pytest.raises(usage.BudgetExceeded):
        voice.synthesize("A different sentence.")


def test_customer_help_escalates():
    queue.add_event("NW-124627", "customer_help", note="still wrong")
    try:
        assert queue.case_detail("NW-124627")["case"]["workflow_status"] == "escalated"
    finally:
        store.get().execute("DELETE FROM case_events WHERE complaint_id = 'NW-124627'")


# ---- Live feed ------------------------------------------------------------------------------

def test_ingest_validates_and_raises_alerts():
    with pytest.raises(ValueError):
        detect_alerts.ingest([{"region": "Atlantis", "month": "2026-10", "signal": "complaints:Other", "value": 5}])
    with pytest.raises(ValueError):
        detect_alerts.ingest([{"region": "Fenwick", "month": "2026-13", "signal": "complaints:Other", "value": 5}])
    res = detect_alerts.ingest([{"region": "Fenwick", "month": "2026-10", "signal": "complaints:Other", "value": 400}])
    try:
        assert any("Fenwick" in a["regions"] for a in res["active_alerts"])
        assert detect_alerts.feed_summary()["ingest"]["points"] == 1
    finally:
        detect_alerts.clear_ingested()
    assert "ingest" not in detect_alerts.feed_summary()


# ---- Auth -----------------------------------------------------------------------------------

@pytest.fixture
def authed(monkeypatch):
    jwt = pytest.importorskip("jwt")
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi.testclient import TestClient
    from api import auth, main

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    monkeypatch.setattr(config, "AUTH_DOMAIN", "tenant.example.com")
    monkeypatch.setattr(config, "AUTH_AUDIENCE", "https://api.northwind-triage")
    monkeypatch.setattr(config, "AUTH_ROLE_MAP", "lead@x.com:lead")
    monkeypatch.setattr(auth, "signing_key", lambda token: key.public_key())

    def token(**claims):
        base = {"iss": "https://tenant.example.com/", "aud": "https://api.northwind-triage", "sub": "auth0|1",
                "exp": int(time.time()) + 600}
        return "Bearer " + jwt.encode({**base, **claims}, key, algorithm="RS256")
    return TestClient(main.app), token


def test_auth_required_and_roles_enforced(authed):
    client, token = authed
    assert client.get("/api/config").status_code == 200                     # public
    assert client.get("/api/queue?limit=1").status_code == 401               # no token
    viewer = {"Authorization": token()}
    assert client.get("/api/queue?limit=1", headers=viewer).status_code == 200
    assert client.post("/api/cases/NW-124358/events", json={"type": "note", "note": "x"}, headers=viewer).status_code == 403
    assert client.post("/api/alerts/inject", headers=viewer).status_code == 403
    lead = {"Authorization": token(email="lead@x.com")}
    assert client.get("/api/me", headers=lead).json()["role"] == "lead"
    assert client.post("/api/alerts/inject", headers=lead).status_code == 403
    analyst = {"Authorization": token(permissions=["alerts:simulate", "cases:write", "intake:create",
                                                   "cases:assign", "signals:write", "demo:reset"])}
    assert client.get("/api/me", headers=analyst).json()["role"] == "analyst"
    assert client.post("/api/alerts/inject", headers=analyst).status_code == 200
    assert client.post("/api/alerts/reset", headers=analyst).status_code == 200
    bad = {"Authorization": token(aud="https://someone-else")}
    assert client.get("/api/queue?limit=1", headers=bad).status_code == 401


def test_api_smoke_auth_off():
    from fastapi.testclient import TestClient
    from api import main
    c = TestClient(main.app)
    cfg = c.get("/api/config").json()
    assert cfg["auth"]["enabled"] is False and cfg["store"]["backend"] == "sqlite"
    assert c.post("/api/assistant/ask", json={"question": "what is the transfer penalty?"}).status_code == 200
    u = c.get("/api/cases/NW-124358/customer-update").json()
    assert u["provider"] in ("browser", "elevenlabs") and "NW" not in u["text"]
    assert c.get("/api/signals").json()["feed"]["derived"]["points"] == 1722
