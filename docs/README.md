# docs/ index (LLM-oriented specs; read instead of code)

Northwind Complaint Triage: hackathon app over a synthetic utility-complaints dataset. Pitch: complaint handling is degrading;
the biggest fixable cause is **transfers between systems**, which depend only on the **entry system**, so route every complaint
once at intake. Three components: **Routing Engine (#1)**, **Operations Dashboard (#3)** and **Triage Queue (#2)**. Two talking points
are stubbed: **#4 auto-answer information-only complaints** and **#6 smart meters for Barrowdale + Dunmoor**. #5 (integration layer) is dropped.
No LLM in any decision; every number shown has a plain-English reason. Optional sponsor adapters (Gemini assistant, ElevenLabs voice, Tiger Data/Postgres storage, Auth0 login, Vultr deploy) sit outside the core. Source plans: `/plan.md` (product), `/plan_integrations.md` (sponsor decisions + costs). `/README.md` = run steps; `/deploy/SETUP.md` = service setup; **`/todo.md` = everything still stubbed, mocked or unverified.**

| Doc | Read when |
|---|---|
| [data.md](data.md) | schemas, value domains, evidence numbers, data caveats |
| [engine.md](engine.md) | any backend logic: baselines, router, queue scoring, alerts, aggregates, formulas |
| [api.md](api.md) | endpoint list + request/response shapes |
| [web.md](web.md) | front-end structure, routes, views, design tokens/rules |
| [integrations.md](integrations.md) | store (SQLite/Postgres/Timescale), signal feed, assistant, voice, auth, usage caps, deploy |
| [decisions.md](decisions.md) | deviations from plan.md, invariants, gotchas, how to extend safely |

## Hard constraints (do not violate)
- `legacy/` is read-only: never edit or delete (user instruction).
- Source DB `Northwind_Challenge_Data/data.db` is opened read-only (`?mode=ro`). All generated state goes in the app store: `data/app.db` (SQLite, default) or Postgres via `DATABASE_URL` (gitignored/rebuildable).
- FOSS mode = no env vars. It must always work fully; every sponsor adapter needs a fallback and must never make a decision.
- Paid services go through `engine/usage.py` caps and caches; no background or per-complaint model calls.
- Fixed as-of date **2026-09-30** (last day in data). All ages, overdue values and "active" alerts are relative to it, never to the wall clock.
- Open-ticket timing comes from dates. **Never use the stored `sla_breach` for open tickets** (it marks 98% breached).
- Router inputs exclude outcome fields: `days_to_close, date_closed, sla_breach, reopened, resolution_action, bill_correction_value` (a unit test guards this).
- Currency is £. Simulated data (alert scenario) must stay labelled "simulated" in the UI.

## Stack / layout
Python 3.10, pandas 2.3, FastAPI + uvicorn; optional psycopg 3, PyJWT. React 18 + Vite 5 + Recharts 2 + @xyflow/react 12 + @auth0/auth0-spa-js (plain JSX, no TS). Windows dev box.
```
engine/  config, store, db, cost_model, build_baselines, router, context, queue_score(+queue_config.json), queue, voice_check (CLI),
         dashboard, replay, planner, usage, assistant, voice
jobs/    detect_alerts (also run as module), rebuild, import_source
api/     main.py (FastAPI, serves web/dist at /), auth.py, auth_check.py (CLI: diagnose Auth0 settings)
web/     src/{App.jsx, api.js, auth.js, session.js, speech.js, format.js, styles.css, components/, views/}
tests/   test_router, test_queue_score, test_baselines_alerts, test_integrations (mocked services, temp store), test_postgres (embedded PG) — 40 tests
deploy/  entrypoint.sh, Caddyfile, SETUP.md;  Dockerfile, docker-compose.yml, .env.example at root
```
Run: `python -m jobs.rebuild --reset` (`--import` on Postgres) → `cd web && npm run build` → `python -m uvicorn api.main:app --port 8000`.
Dev: `npm run dev` (5173, proxies /api→8000). Tests: `pip install -r requirements-dev.txt; python -m pytest tests`.
