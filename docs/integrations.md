# Integrations (sponsor services) — spec

Decisions and justifications are in `/plan_integrations.md`; setup steps in `/deploy/SETUP.md`. This file says how the code works.

## Principle: FOSS core, optional adapters
- **No env vars = "FOSS mode":** SQLite, offline assistant, template briefs, browser speech, auth off. Everything works.
- Sponsor services are optional adapters, each behind one env var, each with a FOSS fallback. No routing, ranking or detection decision depends on them.
- The code targets open standards (PostgreSQL wire protocol, OIDC/JWT, Docker, plain REST via stdlib `urllib`), never vendor SDKs, except `@auth0/auth0-spa-js` (MIT), which is loaded only when auth is on.
- `engine/config.py` reads env vars plus an optional `.env` at the repo root (`setdefault`: the real env wins). All variables are listed in `/.env.example`.

## Storage: `engine/store.py` (Tiger Data)
- `store.get()` is a singleton: `PostgresStore(DATABASE_URL)` if the URL starts with `postgres`, else `SqliteStore(data/app.db)`. `store.use(s)` swaps it (tests). `store.info()` → {backend, timescale, host}.
- **API:**
  - one-shot calls: `execute`, `executemany`, `query` (list of dicts), `scalar`, `df` (DataFrame), `upsert(table, cols, rows, key)`, `has_table`;
  - `transaction()` yields a tx object with the same methods;
  - Postgres only: `copy_df(table, df)` (DROP+CREATE+COPY).
- SQL is written with `?`; Postgres rewrites it to `%s` (and `%` → `%%`). `upsert` = `INSERT OR REPLACE` or `ON CONFLICT DO UPDATE`.
- **Connections:** SQLite opens a new connection per transaction (thread-safe). Postgres keeps one autocommit connection per thread (`threading.local`) and closes it on `OperationalError` so the next call reconnects.
- **Schema** (`_COMMON`, dialect types via `_TYPES`): baselines, alerts, intake_complaints, case_events (serial PK), signal_points, ai_briefs, usage. Indexes on signal_points(region, signal, time) and case_events(complaint_id).
- **Timescale:** in `_after_schema`, on Postgres it tries `CREATE EXTENSION IF NOT EXISTS timescaledb` + `create_hypertable('signal_points','time', if_not_exists, migrate_data)`. On failure it silently falls back to a plain table (`timescale=False`). Only Apache-2 features are used.
- **Source tables:** `db._table(name)` reads from Postgres if the table was imported there (`jobs/import_source.py`, run by `jobs.rebuild --import`); otherwise from the read-only SQLite file.
- **Tested** on embedded Postgres (`pgserver`, no Timescale) by `tests/test_postgres.py`. **Not tested against Tiger Cloud itself** (no account on the dev box).

## Signal feed (`signal_points`, used by `jobs/detect_alerts.py`)
- Columns: time (month-01), month, region, signal, category, value, synthetic (0/1), source ∈ {derived, ingest, simulated}.
- `materialize()` replaces `derived` rows from `build_panel()`. `load_panel(synthetic)` reads the feed, dedupes (region, month, signal) with precedence simulated > ingest > derived, and materializes it if the table is empty.
- `run()` = materialize + `run_detection()`. `run_detection()` = detect on the stored feed (non-synthetic) and replace the real alerts.
- `ingest(points)` validates strictly: region known; month `YYYY-MM`; signal ∈ complaints:<known category> | exceptions_per_1k | estimated_read_rate | sla_breach_rate; value finite and ≥ 0. It replaces same-key ingest rows, inserts, reruns detection, and returns {ingested, active_alerts}. `clear_ingested()` undoes it.
- `inject_scenario()` writes `simulated` rows (synthetic=1) for 2026-10, then detects on `load_panel(synthetic=True)` restricted to that month. `reset_scenario()` deletes the synthetic points and alerts.
- Alert IDs are now deterministic: `AL-|SIM-` + month + sha1(signal|regions)[:6].
- The optional scheduler (`DETECT_INTERVAL_MINUTES` > 0) runs `run_detection()` in a daemon thread.

## Cost guards: `engine/usage.py`
- Table `usage(day UTC, service, units, calls)`. `check(service, units)` raises `BudgetExceeded` before spending; `add()` records after.
- Caps: gemini = `GEMINI_MAX_CALLS_PER_DAY` calls (units = tokens, for info); elevenlabs = `ELEVENLABS_MAX_CHARS_PER_DAY` characters.
- The API maps `BudgetExceeded`→429, `ValueError`→400, `RuntimeError`→502.

## Assistant: `engine/assistant.py` (Gemini)
- **Evidence** items {id, kind ∈ OBSERVED|POLICY|ASSUMPTION|SIMULATED, text}:
  - `base_evidence()`: E1–E14, lru-cached, ~4k chars ≈ 1k tokens. Covers the decline, transfer penalty, entry-system independence (with the "no *recorded* transfers ≠ no handoffs" caveat), slowest 1%, router policy, queue formula, backlog, Replay-is-an-assumption, alert method, focus regions, smart-meter hypothesis, info-only + auto lane, AI-pilot failure, and an app navigation guide.
  - `case_evidence(detail)` → C1–C6 (the four-question summary, rank/why, triage reasons, legacy vs non-transferred).
  - `alert_evidence(alert, linked)` → A1.. (alert, per-region values, shared-system notes, linked open count, a "missing evidence" item).
- `ask(question, history≤6, case_id, alert_id, page)`: builds the evidence list (focus items flagged).
  - With a key: `call_gemini(SYSTEM_PROMPT + rendered evidence, contents)`. Otherwise, or on budget or any error: `offline_answer` (keyword overlap, top 3, each clipped to 260 chars), with a `note` explaining why.
  - Citations `[E#|C#|A#]` that don't exist are stripped. Returns {answer, mode: gemini|offline, model, note, evidence[cited items]}.
- `call_gemini`: POST `https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent`, header `x-goog-api-key`.
  - generationConfig {maxOutputTokens, temperature 0.2, thinkingConfig {thinkingLevel: minimal}}, plus responseMimeType JSON for briefs.
  - On an HTTP 400 mentioning "thinking" it retries once without thinkingConfig. Parts flagged `thought` are skipped. Empty text raises.
- **SYSTEM_PROMPT rules:** evidence only, cite, keep the provenance distinctions, hypotheses as "possible", never make or override decisions, ≤ ~120 words.
- `brief(alert_id, force)` returns {what_changed, possible_explanations, check_next: [{text, cites[]}], mode: gemini|template, cached, created, note, evidence, model}.
  - `_clean_brief` drops bullets with no valid citation, capping at 4 per section and 300 chars.
  - Only Gemini output is cached, in `ai_briefs` keyed by (alert_id, sha1(mode+evidence)), so it regenerates only when the evidence changes. Template briefs are recomputed every time (free).
- `status()` → {gemini, model, usage}.

## Voice: `engine/voice.py` (ElevenLabs)
- `case_update_text(detail)`: a customer-facing template driven by workflow status (new / in_progress / escalated / resolved / auto lane), the owner team, and NEXT_STEP[top resolution action] (plain-English map).
  - Includes the SLA target date if not overdue, otherwise an apology plus "being prioritised"; a "wider issue in your area" line if an alert is linked.
  - The reference is spelled "N W 123888" for speech. It never invents dates and never says "resolved" unless the status is resolved.
- `synthesize(text)` → (mp3 bytes, cached):
  - whitespace-normalised; ≤ `ELEVENLABS_MAX_CHARS_PER_REQUEST` (600) or ValueError; cache `data/tts_cache/sha256(voice|model|format|text).mp3`; budget check → POST `https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=…` with header `xi-api-key` and body {text, model_id}; usage add.
- Browser fallback lives in `web/src/speech.js` (speechSynthesis en-GB). Voice input uses the browser SpeechRecognition (Chrome/Edge only; the button is hidden elsewhere).

## Auth: `api/auth.py` (Auth0 / any OIDC)
- PERMISSIONS: read, assistant:use, cases:write, intake:create, cases:assign, alerts:simulate, signals:write, demo:reset.
- ROLES:
  - viewer = read, assistant:use
  - agent = + cases:write, intake:create
  - lead = + cases:assign
  - analyst = + alerts:simulate, signals:write, demo:reset
- Auth off → `LOCAL_USER` (analyst permissions, `auth: False`).
- Auth on: `Authorization: Bearer <RS256 JWT>` is verified with PyJWT against `https://{AUTH_DOMAIN}/.well-known/jwks.json` (PyJWKClient; `signing_key()` is overridable in tests), checking audience = AUTH_AUDIENCE and issuer = `https://{AUTH_DOMAIN}/`.
- Role resolution: token `permissions` (Auth0 RBAC) → `AUTH_ROLES_CLAIM` list → `AUTH_ROLE_MAP` by email (plain or namespaced claim) or sub → `AUTH_DEFAULT_ROLE`. Nothing requires Auth0's paid features.
- Enforcement: `Depends(require(perm))` per endpoint. `/api/triage` needs intake:create when create=true; events need cases:assign for `assign`, else cases:write. Note/status/assign events get "(by name)" appended when auth is on.
- `/api/config` and `/api/me` are the only endpoints that don't need `read`. `/api/config` exposes no secrets.
- Front end (`web/src/auth.js`): `initAuth(config.auth)` → createAuth0Client (memory cache), handles the redirect callback (restoring the hash via appState); `token()` → getTokenSilently. `api.js` attaches the bearer token when present. The UI disables controls the role lacks (with a tooltip); the server enforces regardless.
- **Backend auth is tested** with a locally generated RSA key. **The SPA login flow is untested** (needs a real tenant).

## Deploy (Vultr + domain)
- `Dockerfile`: node:20 build of `web/`, then python:3.11-slim with the requirements, engine/jobs/api, the source `data.db` and `web/dist`.
- `deploy/entrypoint.sh`: `jobs.rebuild` (`--import` if DATABASE_URL is set) when `REBUILD_ON_START`, then uvicorn on 0.0.0.0:8000.
- `docker-compose.yml`: app + Caddy (`deploy/Caddyfile`, `{$DOMAIN}` gets automatic TLS), volumes for data and certs.
- **Never built on the dev machine** (no Docker there).
