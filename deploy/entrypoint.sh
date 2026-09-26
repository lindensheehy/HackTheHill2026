#!/bin/sh
# Build the app tables (and, on Postgres, import the source tables) before serving.
set -e
if [ "${REBUILD_ON_START:-true}" = "true" ]; then
  if [ -n "$DATABASE_URL" ]; then python -m jobs.rebuild --import; else python -m jobs.rebuild; fi
fi
exec python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
