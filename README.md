# Northwind Complaint Triage

Implementation of [plan.md](plan.md): an intake router, an operations dashboard and a ranked triage queue over the
Northwind challenge data. It uses explainable statistics only, with no LLM.

## Run it

```bash
pip install -r requirements.txt
python -m jobs.rebuild --reset        # builds data/app.db (baselines + alerts); source DB is never written
cd web && npm install && npm run build && cd ..
python -m uvicorn api.main:app --port 8000
```

Open http://127.0.0.1:8000. For front-end development, run `npm run dev` in `web/` (port 5173, proxies `/api` to 8000).

Tests: `python -m pytest tests`

## Layout

| Path | What it is |
|---|---|
| `engine/db.py` | Read-only access to `Northwind_Challenge_Data/data.db`; app tables live in `data/app.db`. As-of date fixed at 2026-09-30 |
| `engine/build_baselines.py` | Learned lookup tables: resolution paths, info-only likelihood, outcomes by transferred/not, transfer rate by entry system, Kaplan-Meier breach curves |
| `engine/router.py` | `route(intake, tables, context)`: a pure function returning the TriageResult (plan §5.3) |
| `engine/queue_score.py` + `queue_config.json` | Queue ranking, computed from dates (the stored `sla_breach` flag is ignored for open tickets) |
| `engine/queue.py` | Open cases + intake complaints + `case_events`, auto-answer lane, case detail |
| `engine/cost_model.py` | Unit costs from `northwind_unit_costs`; per-transfer penalty |
| `engine/dashboard.py`, `replay.py`, `planner.py` | Aggregates for the dashboard, Replay and backlog planner |
| `jobs/detect_alerts.py` | Early warning: z-score vs the region's trailing 6 months, CUSUM drift, grouped across regions with shared systems; simulated scenario |
| `api/main.py` | FastAPI; also serves `web/dist` |
| `web/` | React + Vite + Recharts + React Flow: Operations, Intake, Replay, Triage queue |

## Demo path (plan §10)

1. **Operations:** hero, KPI tiles, SLA degradation, transfer penalty, regions.
2. **Operations → Early warning → Inject scenario:** alerts fire in Barrowdale + Dunmoor and name SYS-01/SYS-06.
3. **Intake:** click "Barrowdale estimated read". The triage card picks up the alert and the account history. Click through to the queue.
4. **Replay:** press play; counters climb at one month per second. Sliders default to 80% adoption and 60% avoidance.
5. **Triage queue:** the routed case is highlighted in place. Open the top case to see "Why is this case #1". The planner and auto-answer lane are sub-tabs.
6. **Reset** (top right) clears demo complaints, events and simulated alerts.

## Deviations from the plan, and why

- **Queue score is continuous through the deadline.** As written, a case one day past SLA scored ~0.05 while one day before scored ~0.86.
  Breached cases now score `w × (1 + overdue_ratio)`, i.e. risk = imminence = 1 plus the overdue ratio.
- **Imminence uses absolute days left** (`1 − days_left / 20`), not `days_left / sla_days`. The plan's version is 0 for every fresh case,
  so a new P1 tied a new P3 at the bottom.
- **Alert threshold is z ≥ 3, not 2.** Across ~1,500 region × signal × month tests, z ≥ 2 fired about 60 times, mostly noise.
  At z ≥ 3 the live feed is quiet (as the plan predicts), and the injected scenario still fires at z = 5–13.
- **Breach risk for open cases** is P(breach | still open at this age), from Kaplan-Meier curves over the last 12 months with open
  cases censored, rather than a flat historical rate.
- **The auto-answer lane takes cases out of the queue:** fresh cases, info-only likelihood ≥ 45%, and a template exists. The queue shows 1,539 plus 60 in the lane (1,599 open).

## Assumptions to label as such

Team names and the owner policy are ours. Headcount (60 FTE) in the planner is an assumption. So are the exception-handling cost
(slider, £34 upper bound) and the "benefit by ~30% coverage" smart-meter hypothesis. The alert scenario is simulated and tagged as such in the UI.
