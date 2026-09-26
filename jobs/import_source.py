"""Copy the six read-only source tables into the configured Postgres store (Tiger Cloud or self-hosted).

Run:  DATABASE_URL=postgresql://... python -m jobs.import_source
The SQLite source file stays the untouched import origin. On SQLite this job is a no-op: the app reads the
source file directly.
"""

import pandas as pd

from engine import db


def main():
    s = db.store()
    if s.dialect != "postgres":
        print("SQLite store: nothing to import (source tables are read in place).")
        return {}
    counts = {}
    with db.source_conn() as conn:
        for name in db.SOURCE_TABLES:
            df = pd.read_sql(f"SELECT * FROM {name}", conn)
            s.copy_df(name, df)
            counts[name] = len(df)
            print(f"{name:28s} {len(df):6d} rows")
    db._table.cache_clear()
    return counts


if __name__ == "__main__":
    main()
