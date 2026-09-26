"""Data access. Source tables are read-only; everything we generate lives in data/app.db."""

import json
import sqlite3
from datetime import date
from functools import lru_cache
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DB = ROOT / "Northwind_Challenge_Data" / "data.db"
APP_DB = ROOT / "data" / "app.db"

# Fixed "as of" date: the last day in the data, so ages and alerts are stable in the demo.
AS_OF = date(2026, 9, 30)
AS_OF_TS = pd.Timestamp(AS_OF)

CLOSED_STATUSES = ("Closed", "Closed - reopened")

APP_SCHEMA = """
CREATE TABLE IF NOT EXISTS baselines (kind TEXT, key TEXT, value TEXT, PRIMARY KEY (kind, key));
CREATE TABLE IF NOT EXISTS alerts (
    alert_id TEXT PRIMARY KEY, month TEXT, signal TEXT, category TEXT, regions TEXT,
    z REAL, shared_systems TEXT, status TEXT, synthetic INTEGER, detail TEXT);
CREATE TABLE IF NOT EXISTS case_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT, complaint_id TEXT, ts TEXT,
    type TEXT, value TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS intake_complaints (
    complaint_id TEXT PRIMARY KEY, date_opened TEXT, channel TEXT, category TEXT,
    priority TEXT, region TEXT, source_system TEXT, account_id TEXT, sla_days INTEGER,
    triage TEXT, created_ts TEXT);
"""


def source_conn():
    return sqlite3.connect(SOURCE_DB.as_uri() + "?mode=ro", uri=True, check_same_thread=False)


def app_conn():
    APP_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(APP_DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(APP_SCHEMA)
    return conn


@lru_cache(maxsize=None)
def _table(name):
    with source_conn() as conn:
        return pd.read_sql(f"SELECT * FROM {name}", conn)


def complaints():
    df = _table("northwind_complaints").copy()
    df["date_opened"] = pd.to_datetime(df["date_opened"])
    df["date_closed"] = pd.to_datetime(df["date_closed"])
    df["is_open"] = df["status"] == "Open"
    df["month"] = df["date_opened"].dt.strftime("%Y-%m")
    return df


def closed_complaints():
    df = complaints()
    return df[~df["is_open"]]


def meter_reads():
    df = _table("northwind_meter_reads").copy()
    df["exceptions_per_1k"] = df["billing_exceptions_raised"] / df["accounts"] * 1000
    return df


def systems():
    return _table("northwind_systems").copy()


def unit_costs():
    return _table("northwind_unit_costs").copy()


def monthly_kpis():
    return _table("northwind_monthly_kpis").copy()


def ai_pilot():
    return _table("northwind_ai_pilot_2025").copy()


def region_systems():
    """region -> list of system ids serving it (latest month)."""
    mr = meter_reads()
    latest = mr[mr["month"] == mr["month"].max()]
    return {r.region: r.systems_serving_region.split("/") for r in latest.itertuples()}


def system_names():
    return dict(zip(systems()["system_id"], systems()["system_name"]))


def label(system_id):
    return f"{system_id} {system_names().get(system_id, '')}".strip()


def dumps(obj):
    return json.dumps(obj, default=_json_default)


def _json_default(o):
    if hasattr(o, "item"):
        return o.item()
    if isinstance(o, (pd.Timestamp, date)):
        return o.isoformat()[:10]
    raise TypeError(type(o))
