"""One small storage layer with two backends: SQLite (default) and PostgreSQL (Tiger Cloud or self-hosted).

SQL is written once with `?` placeholders; the Postgres backend rewrites them. Only portable SQL is used,
plus `upsert()` for the one dialect difference we need. On Postgres, `signal_points` becomes a TimescaleDB
hypertable when the extension is available (Apache-2 features only: hypertables, time_bucket).
"""

import sqlite3
import threading
from contextlib import contextmanager

import pandas as pd

from engine import config

APP_DB_PATH = config.ROOT / "data" / "app.db"

_COMMON = {
    "baselines": "kind TEXT, key TEXT, value TEXT, PRIMARY KEY (kind, key)",
    "alerts": ("alert_id TEXT PRIMARY KEY, month TEXT, signal TEXT, category TEXT, regions TEXT, z {real}, "
               "shared_systems TEXT, status TEXT, synthetic INTEGER, detail TEXT"),
    "intake_complaints": ("complaint_id TEXT PRIMARY KEY, date_opened TEXT, channel TEXT, category TEXT, "
                          "priority TEXT, region TEXT, source_system TEXT, account_id TEXT, sla_days INTEGER, "
                          "triage TEXT, created_ts TEXT"),
    "case_events": "event_id {serial}, complaint_id TEXT, ts TEXT, type TEXT, value TEXT, note TEXT",
    "signal_points": ("time {ts} NOT NULL, month TEXT, region TEXT, signal TEXT, category TEXT, value {real}, "
                      "synthetic INTEGER DEFAULT 0, source TEXT"),
    "ai_briefs": "alert_id TEXT, evidence_hash TEXT, mode TEXT, content TEXT, created_ts TEXT, PRIMARY KEY (alert_id, evidence_hash)",
    "usage": "day TEXT, service TEXT, units {real}, calls INTEGER, PRIMARY KEY (day, service)",
}
_TYPES = {
    "sqlite": {"real": "REAL", "serial": "INTEGER PRIMARY KEY AUTOINCREMENT", "ts": "TEXT"},
    "postgres": {"real": "DOUBLE PRECISION", "serial": "BIGSERIAL PRIMARY KEY", "ts": "TIMESTAMPTZ"},
}
_INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_signal_points ON signal_points (region, signal, time)",
    "CREATE INDEX IF NOT EXISTS ix_case_events ON case_events (complaint_id)",
]


class _Base:
    dialect = ""
    timescale = False

    def ensure_schema(self):
        with self.transaction() as tx:
            for name, cols in _COMMON.items():
                tx.execute(f"CREATE TABLE IF NOT EXISTS {name} ({cols.format(**_TYPES[self.dialect])})")
            for ix in _INDEXES:
                tx.execute(ix)
        self._after_schema()

    def _after_schema(self):
        pass

    # Convenience wrappers: one statement, one transaction.
    def execute(self, sql, params=()):
        with self.transaction() as tx:
            tx.execute(sql, params)

    def executemany(self, sql, rows):
        with self.transaction() as tx:
            tx.executemany(sql, rows)

    def query(self, sql, params=()):
        with self.transaction() as tx:
            return tx.query(sql, params)

    def scalar(self, sql, params=()):
        rows = self.query(sql, params)
        return next(iter(rows[0].values())) if rows else None

    def df(self, sql, params=()):
        with self.transaction() as tx:
            return tx.df(sql, params)

    def upsert(self, table, cols, rows, key):
        with self.transaction() as tx:
            tx.upsert(table, cols, rows, key)

    def has_table(self, name):
        raise NotImplementedError


class _Tx:
    """Operations inside one transaction. `_cur()` gives a DB-API cursor; `_sql()` adapts placeholders."""

    def __init__(self, conn, dialect):
        self.conn, self.dialect = conn, dialect

    def _sql(self, sql):
        return sql if self.dialect == "sqlite" else sql.replace("%", "%%").replace("?", "%s")

    def execute(self, sql, params=()):
        cur = self.conn.cursor()
        cur.execute(self._sql(sql), tuple(params))
        return cur

    def executemany(self, sql, rows):
        rows = [tuple(r) for r in rows]
        if rows:
            self.conn.cursor().executemany(self._sql(sql), rows)

    def query(self, sql, params=()):
        cur = self.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def df(self, sql, params=()):
        cur = self.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return pd.DataFrame.from_records(cur.fetchall(), columns=cols)

    def upsert(self, table, cols, rows, key):
        marks = ",".join("?" * len(cols))
        if self.dialect == "sqlite":
            sql = f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({marks})"
        else:
            updates = ",".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in key)
            sql = (f"INSERT INTO {table} ({','.join(cols)}) VALUES ({marks}) "
                   f"ON CONFLICT ({','.join(key)}) DO " + (f"UPDATE SET {updates}" if updates else "NOTHING"))
        self.executemany(sql, rows)


class SqliteStore(_Base):
    dialect = "sqlite"

    def __init__(self, path=APP_DB_PATH):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()

    @contextmanager
    def transaction(self):
        # A fresh connection per transaction: safe across FastAPI's worker threads.
        conn = sqlite3.connect(self.path, check_same_thread=False)
        try:
            with conn:
                yield _Tx(conn, self.dialect)
        finally:
            conn.close()

    def has_table(self, name):
        return bool(self.query("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (name,)))


class PostgresStore(_Base):
    dialect = "postgres"

    def __init__(self, url):
        import psycopg  # optional dependency, only needed with DATABASE_URL
        self._psycopg = psycopg
        self.url = url
        self._local = threading.local()
        self.ensure_schema()

    def _conn(self):
        conn = getattr(self._local, "conn", None)
        if conn is None or conn.closed:
            conn = self._psycopg.connect(self.url, autocommit=True)
            self._local.conn = conn
        return conn

    @contextmanager
    def transaction(self):
        conn = self._conn()
        try:
            with conn.transaction():
                yield _Tx(conn, self.dialect)
        except self._psycopg.OperationalError:
            conn.close()  # reconnect next time (e.g. idle connection dropped by the host)
            raise

    def _after_schema(self):
        # TimescaleDB is present on Tiger Cloud. Hypertables are Apache-2 licensed.
        try:
            with self.transaction() as tx:
                tx.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
            with self.transaction() as tx:
                tx.execute("SELECT create_hypertable('signal_points', 'time', if_not_exists => TRUE, migrate_data => TRUE)")
            self.timescale = True
        except Exception:
            self.timescale = False

    def has_table(self, name):
        return bool(self.query("SELECT 1 AS x FROM information_schema.tables WHERE table_name = ?", (name,)))

    def copy_df(self, table, df):
        """Replace `table` with the frame's contents using COPY (fast over a network link)."""
        types = {"int64": "BIGINT", "float64": "DOUBLE PRECISION"}
        cols = ", ".join(f'"{c}" {types.get(str(t), "TEXT")}' for c, t in df.dtypes.items())
        conn = self._conn()
        with conn.transaction():
            cur = conn.cursor()
            cur.execute(f'DROP TABLE IF EXISTS "{table}"')
            cur.execute(f'CREATE TABLE "{table}" ({cols})')
            names = ", ".join(f'"{c}"' for c in df.columns)
            with cur.copy(f'COPY "{table}" ({names}) FROM STDIN') as cp:
                for row in df.astype(object).where(df.notna(), None).itertuples(index=False):
                    cp.write_row(row)


_store = None
_lock = threading.Lock()


def get():
    global _store
    if _store is None:
        with _lock:
            if _store is None:
                _store = PostgresStore(config.DATABASE_URL) if config.DATABASE_URL.startswith("postgres") else SqliteStore()
    return _store


def use(store):
    """Swap the active store (tests, tools). Returns the previous one."""
    global _store
    prev, _store = _store, store
    return prev


def info():
    s = get()
    return {"backend": s.dialect, "timescale": s.timescale,
            "host": "Tiger Cloud" if "tsdb.cloud" in getattr(s, "url", "") else ("SQLite file" if s.dialect == "sqlite" else "PostgreSQL")}
