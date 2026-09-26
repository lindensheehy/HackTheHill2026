"""Load every CSV in Northwind_Challenge_Data/ into data/data.db and document the schema in data/schema.md.

Paths resolve relative to the repo root, so this can be run from any directory:
    python database_migration/database_migration.py
"""

import csv
import re
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_DIR = REPO_ROOT / "Northwind_Challenge_Data"
DATA_DIR = REPO_ROOT / "data"
DB_PATH = DATA_DIR / "data.db"
SCHEMA_PATH = DATA_DIR / "schema.md"

# Integers without leading zeros, so IDs like "00123" stay TEXT and keep their padding.
INT_RE = re.compile(r"^-?(0|[1-9]\d*)$")
REAL_RE = re.compile(r"^-?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?$")
DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?)?$")


def infer_type(values):
    """Pick the narrowest SQL type that fits every non-empty value in a column."""
    present = [v for v in values if v != ""]
    if not present:
        return "TEXT"
    if all(INT_RE.match(v) for v in present):
        return "INTEGER"
    if all(REAL_RE.match(v) for v in present):
        return "REAL"
    if all(DATETIME_RE.match(v) for v in present):
        return "DATETIME"
    return "TEXT"


def convert(value, sql_type):
    if value == "":
        return None
    if sql_type == "INTEGER":
        return int(value)
    if sql_type == "REAL":
        return float(value)
    # DATETIME is stored as ISO-8601 text, which SQLite's date functions understand.
    return value


def quote(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def load_csv(conn, csv_path):
    table = csv_path.stem
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = [row for row in reader if row]

    columns = list(zip(*rows)) if rows else [()] * len(header)
    types = [infer_type(col) for col in columns]

    col_defs = ", ".join(f"{quote(name)} {t}" for name, t in zip(header, types))
    placeholders = ", ".join("?" for _ in header)

    conn.execute(f"DROP TABLE IF EXISTS {quote(table)}")
    conn.execute(f"CREATE TABLE {quote(table)} ({col_defs})")
    conn.executemany(
        f"INSERT INTO {quote(table)} VALUES ({placeholders})",
        ([convert(v, t) for v, t in zip(row, types)] for row in rows),
    )
    print(f"Loaded {len(rows):>6} rows into {table}")
    return table


def write_schema(conn, tables):
    lines = ["# Database Schema", "", f"Source database: `{DB_PATH.name}`", ""]
    for table in tables:
        (row_count,) = conn.execute(f"SELECT COUNT(*) FROM {quote(table)}").fetchone()
        lines += [f"## {table}", "", f"Rows: {row_count}", "", "| Column | Type |", "| --- | --- |"]
        for _, name, col_type, *_ in conn.execute(f"PRAGMA table_info({quote(table)})"):
            lines.append(f"| {name} | {col_type} |")
        lines.append("")
    SCHEMA_PATH.write_text("\n".join(lines), encoding="utf-8")


def main():
    csv_paths = sorted(CSV_DIR.glob("*.csv"))
    if not csv_paths:
        print(f"No CSV files found in {CSV_DIR}.")
        return

    DATA_DIR.mkdir(exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        tables = [load_csv(conn, path) for path in csv_paths]
        write_schema(conn, tables)
    conn.close()

    print(f"Wrote {DB_PATH} and {SCHEMA_PATH}")


if __name__ == "__main__":
    main()
