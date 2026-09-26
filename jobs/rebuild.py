"""Rebuild every generated table in the app store from the read-only source data.

Run:  python -m jobs.rebuild            (keeps demo state: intake complaints, case events, ingested points)
      python -m jobs.rebuild --reset    (also clears demo state and simulated alerts)
      python -m jobs.rebuild --import   (Postgres only: first copy the source tables into the database)
"""

import sys

from engine import build_baselines, queue, store
from jobs import detect_alerts, import_source


def main(reset=False, do_import=False):
    print("store:", store.info())
    if do_import:
        import_source.main()
    tables = build_baselines.build()
    print("baselines:", {k: len(v) for k, v in tables.items()})
    alerts = detect_alerts.run()
    print("signal feed:", detect_alerts.feed_summary())
    print(f"alerts: {len(alerts)} real ({sum(a['status'] == 'active' for a in alerts)} active)")
    if reset:
        queue.reset_demo()
        print("demo state cleared")


if __name__ == "__main__":
    main(reset="--reset" in sys.argv, do_import="--import" in sys.argv)
