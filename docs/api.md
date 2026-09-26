# API (`api/main.py`, FastAPI, prefix `/api`)

Startup: load baselines (build if empty), run alert detection if the alerts table is empty, warm the dashboard cache, and start the detector thread if DETECT_INTERVAL_MINUTES > 0.
**Permissions** (api/auth.py) guard every route: `read` unless noted. With auth off, everyone has all of them. 401 = no or bad token; 403 = the role lacks the permission.
Errors from optional services: 429 budget cap, 400 invalid input, 502 upstream failure.
`/api/dashboard` and `/api/replay` are `lru_cache`d in-process: **restart the server after `jobs.rebuild`**.
If `web/dist` exists, `/assets` is mounted and every other non-API path returns `index.html` (SPA). CORS is open.

| Method & path | Params / body | Returns |
|---|---|---|
| GET /api/meta | – | {as_of, channels[], categories[], regions[], priorities[], sla_days{}, teams[], entry_systems[{id,name}] (01,03,04,05), channel_entry{}, examples[{title, blurb, intake}]} |
| POST /api/triage (intake:create; read if create=false) | body Intake {channel, category, priority, region, account_id?, entry_system?}; query `create` (default true) | TriageResult (engine.md). With create=true the complaint is persisted and the result gains queue_rank, queue_size, in_auto_lane. 400 if priority is invalid |
| GET or POST /api/replay | – | replay() payload |
| GET /api/queue | strict, region, category, priority, owner, system, search, limit (≤2000, default 100), offset | {rows[], summary{}, config{}, strict} |
| GET /api/queue/auto | – | auto_lane() |
| GET /api/cases/{id} | – | case_detail(); 404 if unknown |
| POST /api/cases/{id}/events (cases:write; assign needs cases:assign) | {type: assign\|status\|note\|auto_bounce\|customer_help, value?, note?}; for status, value ∈ in_progress\|resolved\|escalated | updated case_detail(); 400 if invalid |
| GET /api/planner | – | planner.defaults() |
| GET /api/dashboard | – | {kpis, monthly, transfer, regions, heatmap, smart_meter, talking_points} |
| GET /api/graph | – | graph(active alerts) |
| GET /api/alerts | status? | {alerts[], scenario, feed, store} |
| GET /api/alerts/{id} | – | {alert, series{region:[{month, v, simulated, source}]} (read from signal_points; includes simulated points only for synthetic alerts), linked_open[] (≤50 queue rows in the alert's regions and related categories, score desc), linked_open_total} |
| POST /api/alerts/inject (alerts:simulate) | – | {alerts[] (new synthetic), scenario} |
| POST /api/alerts/reset (alerts:simulate) | – | {ok} (removes synthetic alerts and points) |
| POST /api/demo/reset (demo:reset) | – | {ok} (intake complaints, case events, synthetic alerts and points cleared) |
| GET /api/config (public) | – | {as_of, auth{enabled, domain, client_id, audience}, store{backend, timescale, host}, ai{gemini, model}, voice{elevenlabs, model, max_chars_per_request}} |
| GET /api/me (any valid user) | – | {sub, name, role, permissions[], auth} |
| GET /api/usage | – | usage.summary(): per service {unit, cap, used, calls, tokens_or_chars} |
| POST /api/assistant/ask (assistant:use) | {question, history[{role, text}], case_id?, alert_id?, page?} | {answer, mode: gemini\|offline, model, note, evidence[{id, kind, text}]} |
| POST /api/assistant/brief/{alert_id} (assistant:use) | query force | brief (see integrations.md); 404 if no alert |
| GET /api/cases/{id}/customer-update | – | {text, provider: elevenlabs\|browser}; 404 if closed or unknown |
| GET /api/cases/{id}/customer-update/audio (assistant:use) | – | audio/mpeg, header X-Cache hit\|miss. Text is server-side only. 502 if ElevenLabs is off or fails |
| POST /api/voice/tts (assistant:use) | {text ≤ 600 chars} | audio/mpeg (assistant read-aloud) |
| GET /api/signals | – | {feed{source:{points, first, last}}, store} |
| POST /api/signals (signals:write) | [{region, month, signal, value}] | {ingested, active_alerts[]}; 400 on validation |
| DELETE /api/signals (signals:write) | – | {ok}: removes ingested points, reruns detection |

Prepared examples (`EXAMPLES`), as channel / category / priority / region / account / entry:
1. Barrowdale estimated read: Phone, Billing - estimated read, P2, Barrowdale, ACC-980200, SYS-05. Picks up the scenario alert and 2 prior complaints.
2. Disputed bill via web: Web form, Billing - disputed amount, P3, Fenwick, ACC-730009, SYS-03.
3. Poor communication by email: Email, Service - poor communication, P3, Ashford, ACC-615081, SYS-05. Goes to the auto lane.
4. Regulator referral, supply outage: Regulator referral, Supply - interruption, P1, Dunmoor, ACC-489331, SYS-05.

Test client note: Starlette's TestClient wants `httpx2` but falls back to `httpx` (installed; this prints a deprecation warning). Don't install `httpx2`.
