"""Rebuild every generated table in data/app.db from the read-only source data.

Run:  python -m jobs.rebuild            (keeps demo state: intake complaints, case events)
      python -m jobs.rebuild --reset    (also clears demo state and simulated alerts)
"""

import sys

from engine import build_baselines, queue
from jobs import detect_alerts


def main(reset=False):
    tables = build_baselines.build()
    print("baselines:", {k: len(v) for k, v in tables.items()})
    alerts = detect_alerts.run()
    print(f"alerts: {len(alerts)} real ({sum(a['status'] == 'active' for a in alerts)} active)")
    if reset:
        queue.reset_demo()
        print("demo state cleared")


if __name__ == "__main__":
    main(reset="--reset" in sys.argv)
