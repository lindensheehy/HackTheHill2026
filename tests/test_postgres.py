"""End-to-end run of the Postgres backend (the Tiger Data path) on an embedded server.

Skipped unless `pgserver` and `psycopg` are installed (requirements-dev.txt). The embedded server has no
TimescaleDB, so this exercises the plain-Postgres fallback; on Tiger Cloud the same code creates a hypertable.
"""

import os
import tempfile

import pytest

pgserver = pytest.importorskip("pgserver")
pytest.importorskip("psycopg")

from engine import build_baselines, db, queue, store  # noqa: E402
from jobs import detect_alerts, import_source  # noqa: E402


@pytest.fixture(scope="module")
def pg():
    srv = pgserver.get_server(os.path.join(tempfile.gettempdir(), "nw_pgtest"), cleanup_mode="stop")
    srv.psql("DROP DATABASE IF EXISTS nw_test;")
    srv.psql("CREATE DATABASE nw_test;")
    url = srv.get_uri().rsplit("/", 1)[0] + "/nw_test"
    prev = store.use(store.PostgresStore(url))
    db._table.cache_clear()
    build_baselines.load.cache_clear()
    yield store.get()
    store.use(prev)
    db._table.cache_clear()
    build_baselines.load.cache_clear()


def test_full_pipeline_on_postgres(pg):
    counts = import_source.main()
    assert counts["northwind_complaints"] == 25416
    assert pg.has_table("northwind_complaints")
    assert len(db.complaints()) == 25416              # now read from Postgres, not the SQLite file

    tables = build_baselines.build()
    assert round(tables["global"]["transfer_penalty"]["days"]["transferred"], 1) == 38.2

    alerts = detect_alerts.run()
    assert len(alerts) == 23 and not any(a["status"] == "active" for a in alerts)
    assert detect_alerts.feed_summary()["derived"]["points"] == 1722

    sim = detect_alerts.inject_scenario()
    grouped = [a for a in sim if a["regions"] == ["Barrowdale", "Dunmoor"]]
    assert grouped and all(set(a["shared_systems"]) == {"SYS-01", "SYS-06"} for a in grouped)

    t = queue.create_intake({"channel": "Phone", "category": "Billing - estimated read", "priority": "P2",
                             "region": "Barrowdale", "account_id": "ACC-980200", "entry_system": "SYS-05"})
    assert t["context"]["region_alert_id"] and t["context"]["account_prior_complaints"] == 2
    queue.add_event(t["complaint_id"], "status", "in_progress")
    detail = queue.case_detail(t["complaint_id"])
    assert detail["case"]["workflow_status"] == "in_progress"
    assert detail["triage"]["legacy_route"]["entry_system"].startswith("SYS-05")

    res = detect_alerts.ingest([{"region": "Fenwick", "month": "2026-10", "signal": "complaints:Other", "value": 400}])
    assert res["ingested"] == 1 and any("Fenwick" in a["regions"] for a in res["active_alerts"])
    detect_alerts.clear_ingested()

    queue.reset_demo()
    assert pg.scalar("SELECT COUNT(*) AS n FROM signal_points WHERE synthetic = 1") == 0
    assert pg.scalar("SELECT COUNT(*) AS n FROM intake_complaints") == 0
