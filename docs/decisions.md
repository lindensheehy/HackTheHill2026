# Decisions, deviations, gotchas, extension rules

## Deviations from plan.md (intentional; keep unless the user says otherwise)
| Plan | Implemented | Why |
|---|---|---|
| `data/data.db` holds source + app tables | Source is `Northwind_Challenge_Data/data.db` (read-only); app tables in the app store (`data/app.db`, or Postgres via `DATABASE_URL`) | Keeps the source immutable; the app store can be rebuilt |
| "No LLM" pitch | "Routing and prioritisation use explainable rules; optional AI (Gemini) helps people read the evidence and never decides" | Adding the Gemini assistant (plan_integrations.md) |
| Replay and triage card show router "savings" / "Routed" | Replay is an "assumption-based scenario"; the card compares Legacy with "Not transferred" history; router reasons never say "saves"; CaseTrack has "no *recorded* transfers" | Historical differences aren't a measured effect of routing (external review) |
| Alerts computed from an in-memory panel | Detection reads the stored `signal_points` feed (derived / ingest / simulated) | Makes the database part of the demonstrated workflow (Tiger Data) and enables live ingestion |
| score (breached) = w·overdue_ratio; imminence = 1 − days_left/sla | breached: w·(1+ratio); imminence = 1 − days_left/20 | The plan's version drops from ~0.86 to ~0.05 at the deadline, and scores every fresh case 0 (a new P1 tied a new P3) |
| Alert z ≥ 2 | z ≥ 3, Poisson sd floor, lift ≥ 1.3, count ≥ 10; CUSUM fires once per region | z ≥ 2 gave ~60 alerts from ~1,500 tests (noise). The scenario still fires at z = 5–13 |
| breach_risk = historical rate | Kaplan-Meier P(breach \| open at age), last 12 months, open cases censored | Honest under censoring and current performance |
| Alert bonus not specified | +0.25 alert_bonus in queue score | Surfaces cases linked to a live regional alert |
| Auto lane is a "tab" stub | The lane actually removes qualifying fresh cases from the queue until bounced | Makes #4 demonstrable; the queue shows 1,539 + 60 in the lane |
| Replay "streamed or paged" | A single GET returns month/week aggregates; animation is client-side | Sliders update instantly |
| Streamlit fallback | Not built (React done) | – |
| Gradient-boosted expected-days model (P2) | **Not built** | Optional stretch; would need scikit-learn and a time split (train Oct-24–Mar-26, test Apr–Sep-26) |

## Invariants guarded by tests (`python -m pytest tests`, 40 tests)
- **Integrations** (test_integrations.py, temp store, all services mocked):
  - offline and Gemini answers cite only real evidence; the budget cap and failures fall back offline;
  - briefs drop uncited bullets and cache Gemini output; the voice template follows status and never claims "resolved";
  - TTS is cached and capped (per request and per day); customer_help escalates;
  - ingest validates and raises alerts;
  - auth: 401 without a token, roles enforced (viewer/lead/analyst via map or permissions), wrong audience rejected.
- **Postgres** (test_postgres.py, embedded server): full pipeline incl. import, detection, scenario, intake, events, ingest and reset.
- **Router:**
  - owner is always CaseTrack, team = TEAMS[category];
  - resolution shares are sorted and sum to ≤ 1;
  - routed ≤ legacy on days, breach and cost;
  - CaseTrack entry → risk 0 and legacy == routed; other entries → risk in 0.44–0.49;
  - channel default entry; Barrowdale billing links SYS-01 + SYS-06 plus the no-smart-meter reason; the alert/context pass-through;
  - **outcome fields ignored**; `route` doesn't mutate the tables.
- **Queue score** (synthetic frames, flat 0.8 survival):
  - timing from dates;
  - equal overdue ratio → higher priority first; a P3 100 days over beats a P1 1 day over;
  - breached always above just-before-deadline;
  - imminence ordering, amber/green states, transferred tie-break, strict mode order;
  - reasons present; a fresh P1 outranks a fresh P3.
- **Baselines/alerts:**
  - penalty 38.2/23.0/£53; survival curves valid and ending at 1.0; SYS-04 rate 0;
  - the scenario groups Barrowdale + Dunmoor with shared {SYS-01, SYS-06};
  - the real feed has ≤ 2 active alerts.

## Gotchas
- **The older tests mutate app.db:** test_baselines_alerts calls `reset_scenario()`, which wipes simulated alerts and points from a live demo. test_integrations and test_postgres use their own temporary stores.
- The API caches dashboard/replay per process, and baselines via `build_baselines._cache`. After `jobs.rebuild`, restart uvicorn.
- Alert IDs are deterministic (sha1 of signal and regions) but still regenerate when the detection output changes.
- "It's using the Windows voice": ElevenLabs is either not configured on the *running* server, or it returned an error. The UI shows which; `python -m engine.voice_check` diagnoses the key. The browser fallback is deliberate (`VOICE_BROWSER_FALLBACK`).
- Auth0 "Oops!, something went wrong" = Auth0 rejected the /authorize request (unknown client, callback mismatch, service not found). It is not an app crash. Run `python -m api.auth_check`, and see deploy/SETUP.md §4. `.env` is read only at start-up: restart after editing it.
- Sponsor adapters: never let one raise into core flows. Wrap calls (see `assistant.ask`) and fall back to FOSS behaviour. Gemini model IDs change often: `GEMINI_MODEL` is config, and 2.5 Flash-Lite retires on 16 Oct 2026.
- Postgres: SQL must stay portable (`?` placeholders, no SQLite-only syntax except through `store.upsert`). Test with `tests/test_postgres.py`.
- `/api/dashboard` takes ~3 s on a cold call (warmed at startup). Queue endpoints recompute scores per request (~0.25 s); acceptable for 1.6k rows.
- The intake complaint's own `source_system` is SYS-04; its original entry system lives only in `triage.legacy_route.entry_system`.
- Windows + Git Bash: use `python -m uvicorn`; stop the server by PID on port 8000. Console output mangles "£" (display only).
- **Don't hard-code evidence numbers in UI copy;** read them from the API. Exceptions: plan-level labels, e.g. "breach 88% / reopen 29%" in the queue `why` text, and the "~1.5×" heatmap note.
- The breach headline says 93% (Jun-26 cohort); plan.md says ~92%. The code is right; decks should say "about 92–93%".

## Extending safely
- New learned table: add a function in build_baselines, add it to the `tables` dict in `build()`, and read it via `load()[kind]`. Keep keys as `|`-joined intake-time attributes only.
- Change ranking: edit `engine/queue_config.json` (it's shown in the UI) or `score_frame`. Update `_why` so every score stays explained, and extend `tests/test_queue_score.py`.
- New alert signal: emit rows in `build_panel()`, map it in `SIGNAL_CATEGORY` if it relates to complaint categories, add a label in `signal_label`.
- New endpoint: thin wrapper in api/main.py over an engine function that returns JSON-able dicts (use `queue.rows()` for frames: it converts NaN→None and formats dates).
- New view: add it to `TABS` in App.jsx, create views/X.jsx, use Card/Tip/Legend/axisProps and the tokens. Rebuild `web/dist` for the FastAPI-served version.
- Any generated state goes in the app store through `db.store()` (portable SQL; add the table to `store._COMMON`), and `queue.reset_demo()` should clear demo-created state.
- New sponsor or paid service: read its key in `engine/config.py`, gate spending with `usage.check`/`usage.add` (add a LIMITS entry), cache results, give it a FOSS fallback, catch every error in the calling path, surface status in `/api/config`, guard the endpoint with a permission, and mock it in tests (never call real services from tests).
