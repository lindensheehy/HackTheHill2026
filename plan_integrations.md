# Sponsor & Mini-Challenge Integration Plan

Companion to [plan.md](plan.md). It decides, for every Hack the Hill mini-challenge and MLH category, whether we build it,
how central it is, why, what it costs to run, and where it lives in the code. Guiding rule from the team: **nothing may
push up running costs without a stated justification, and every integration has to fit the existing workflow.**

---

## 1. The midstep: what we evaluated

### 1.1 What we already have (the baseline we must not break)
- Router, triage queue, dashboard and alerts built on pandas + FastAPI + React + SQLite: 100% open source, £0 to run locally.
- Every number is explained in plain English; no LLM is involved in any decision.
- The demo works offline.

### 1.2 The tension that decides everything: Best FOSS
Best FOSS disqualifies a project if *"a proprietary API, platform, or service provides part of the project's core functionality"*.
Every sponsor API (Gemini, ElevenLabs, Auth0, Tiger Cloud, Vultr) is proprietary, so we define **core** strictly and keep
every sponsor service **outside** it:

| Layer | Examples | Rule |
|---|---|---|
| **Core** (must be FOSS) | Routing policy, queue ranking, alert detection, dashboard aggregates, storage schema, UI | Only OSS code and libraries. Runs with zero keys |
| **Pluggable host** | Where Postgres runs (Tiger Cloud or self-hosted), where the app runs (Vultr or any VM), which OIDC provider (Auth0 or Keycloak) | Code targets the open standard (PostgreSQL wire protocol, OIDC/JWT, Docker), never a vendor SDK |
| **Optional assistive add-on** | Gemini assistant and briefs, ElevenLabs speech | Off without a key; a FOSS fallback replaces each one; no core decision depends on it |

**"FOSS mode" is the default configuration** (no `.env`): SQLite, the offline template assistant, browser speech, auth off.
We submit to Best FOSS stating exactly this. **Residual risk:** a judge may still count the hosted demo's use of Tiger Cloud
as core. The mitigation is that the same image runs unchanged on self-hosted PostgreSQL (`DATABASE_URL` only), and we only use
Apache-2-licensed TimescaleDB features. The team decides on the Devpost checkbox.

### 1.3 Cost envelope (verified Sept 2026; re-check before submitting)
| Service | Plan we'd use | Our expected usage | Expected cost |
|---|---|---|---|
| Gemini API | Free tier (AI Studio key); paid fallback `gemini-3.1-flash-lite` at $0.25 / $1.50 per M tokens in/out | ≤ 300 calls/day cap, ~4k in + ≤ 700 out tokens | Free tier covers it; worst case ≈ $0.60/day at the cap |
| ElevenLabs | Free Creator month (131k credits) from the event | Flash model ≈ 0.5 credit/char; spoken updates ≈ 250 chars; audio cached by text hash; daily cap 15k chars | ≈ 7.5k credits/day at the cap, so the free month is more than enough |
| Tiger Data | Tiger Cloud free plan | < 50 MB (25k complaints, 3.5k signal points, events) | $0 (paid would be ≥ $30/month; not needed) |
| Vultr | Cloud Compute 1 vCPU / 1 GB | 1 container (API + built UI + scheduler) | $5/month (MLH credits often cover it) |
| Auth0 | Free (25k MAU) | < 20 users | $0. We do **not** rely on paid RBAC: roles come from an app-side role map, or a token claim if configured |
| GoDaddy Registry domain | MLH claim code or cheapest TLD | 1 domain | $0 to ~$15/year |

Hard cost guards in code: per-day caps in the `usage` table, per-request size caps, caching (briefs by evidence hash,
audio by text hash), no per-complaint model calls, no background model calls, and every model call triggered by a click.

---

## 2. Decisions

| # | Challenge | Decision | Where it sits | One-line justification |
|---|---|---|---|---|
| 1 | **Best UI/UX** | **Build: core** | Core | Zero cost; judged on the same demo; it also fixes credibility issues (provenance labels) |
| 2 | **Best FOSS** | **Enter** (default mode) | Core | Already true of the core; we keep it true by construction (§1.2) |
| 3 | **Gemini API** | **Build: assistive** | Add-on | "Ask Northwind" helps judges and staff *learn the problem and the app*, and turns alert evidence into a cited brief. It reads our numbers; it never decides |
| 4 | **ElevenLabs** | **Build: assistive** | Add-on | Accessible spoken case updates for customers, generated from the live case state with template text (no LLM); assistant answers can be read aloud |
| 5 | **Tiger Data** | **Build: storage option** | Pluggable host | The alert pipeline becomes a real operational time-series feed (`signal_points` hypertable plus an ingest endpoint). Justified by the proposed live feed, **not** by volume (our data is small) |
| 6 | **Vultr** | **Build deploy kit**; the team runs the deploy | Pluggable host | Judges need a hosted URL; $5/month; one container including the scheduled detector |
| 7 | **Auth0** | **Build: optional** | Pluggable host | Complaint data identifies customers (account IDs), so a real deployment must gate it. Permissions are enforced in FastAPI, not just by hiding buttons. Standard OIDC, so Keycloak works too |
| 8 | **GoDaddy domain** | **Config only** (Caddy + `DOMAIN`) | Deploy | Automatic TLS for the Vultr host; buying the domain is a team action |
| 9 | Best Hardware Hack | **Reject** | – | No hardware in a complaint-triage workflow; bolting on a peripheral fails the rule ("simply connecting a peripheral… is not enough") |
| 10 | MathemaTech (education) | **Reject** | – | Explaining our own app to judges isn't "improving access to education". Claiming it would be a stretch judges will see through |
| 11 | Solana | **Reject** | – | A ledger adds cost and complexity and solves no problem in complaint handling |
| 12 | Presage (vitals/emotion) | **Reject** | – | Sensing agents' or customers' vitals is invasive, off-mission, and a privacy liability for a regulated utility |

### Corrections adopted from review (credibility > logos)
- **Replay** is relabelled an **assumption-based scenario**: historical transferred-vs-not differences, applied under slider assumptions. It is not a measured effect of the router.
- The "Routed" column is renamed **"Non-transferred history"** on the triage card and flagged as an expectation, not a guarantee.
- **CaseTrack's zero recorded transfers** is noted as "no *recorded* transfers": it doesn't prove there are no operational handoffs.
- Pitch line becomes: *"Routing and prioritisation use explainable rules. Optional AI helps people read the evidence; it never decides."*

---

## 3. What gets built, and where

### 3.1 UI/UX (core)
- **Provenance labels everywhere** (`<Provenance kind>`): Historical observation · Proposed policy · Assumption-based scenario · Simulated · AI-generated.
- **Connected journey:** region card → "Investigate" (alerts for the region + open complaints) → queue pre-filtered via `#/queue?region=…` → case drawer → action → queue updates.
- **Case drawer answers four questions first:** What happened · What happens next · Who owns it · What's blocking it. The blockers come from deterministic rules (transferred history gap, past SLA, awaiting field visit via FieldForce, regional alert, escalated).
- **Keyboard:** `/` search, `j`/`k` or ↑/↓ to move, Enter to open, Esc to close, `?` for help. Visible focus rings; every status colour also has a text label.
- **Files:** `web/src/components/{Provenance,Assistant,CustomerUpdate}.jsx`, `views/Queue.jsx`, `views/Dashboard.jsx`, `engine/queue.py` (`blockers`, `next_action`).

### 3.2 Gemini: "Ask Northwind" + investigation briefs (add-on)
- `engine/assistant.py` builds an **evidence pack** (`E1…En`, each tagged observed/policy/assumption/simulated) from our own aggregates, plus the focused case or alert.
- **Chat:** a floating panel on every page, sent with the page context. The system prompt allows answers only from the evidence, cites `[E#]`, labels hypotheses, and never recommends overriding a queue decision.
- **Brief:** `POST /api/assistant/brief/{alert_id}` returns JSON with three sections (What changed · Possible explanations · What to check next). Each bullet cites evidence IDs; invalid citations are dropped. Cached in `ai_briefs` by evidence hash, so it regenerates only when the evidence changes.
- **Fallback (FOSS mode):** keyword retrieval over the same evidence pack, and a deterministic template brief, both labelled "AI off".
- **Costs:** model `gemini-3.1-flash-lite` (env `GEMINI_MODEL`), `thinkingLevel: minimal`, `maxOutputTokens` 700, `GEMINI_MAX_CALLS_PER_DAY` 300.

### 3.3 ElevenLabs: spoken updates (add-on)
- `engine/voice.py` fills a template for each case state: received / in progress / escalated / resolved + next step + SLA date. It never invents repair dates and never marks anything resolved.
- **Case drawer "Customer update" card:** transcript, ▶ Play, and "I still need help", which logs an event and escalates the case (a visible workflow effect).
- **Assistant:** 🔊 reads an answer aloud; 🎤 voice question via the browser's speech recognition where available.
- **Costs:** `eleven_flash_v2_5`, `mp3_22050_32`; cache `data/tts_cache/<sha256>.mp3`; ≤ 600 chars per request; `ELEVENLABS_MAX_CHARS_PER_DAY` 15000.
- **Fallback:** browser `speechSynthesis`.

### 3.4 Tiger Data: operational time-series store (pluggable host)
- `engine/store.py` is one small DB layer with SQLite (default) and PostgreSQL backends (psycopg 3). Setting `DATABASE_URL` switches everything.
- New table `signal_points(time, month, region, signal, category, value, synthetic)`. It's a **hypertable** when the `timescaledb` extension exists (Tiger Cloud); a plain table otherwise.
- **Detection reads from the DB.** Inject writes synthetic points to the DB, then detection runs; reset deletes them. `POST /api/signals` ingests external metric points, which is the ongoing-feed story.
- `jobs/import_source.py` copies the six source tables into Postgres (COPY), so complaints, meter stats, case events and alerts all live in Tiger.
- **Apache-only:** hypertables and `time_bucket`. No continuous aggregates or compression (those are TSL-licensed).

### 3.5 Auth0 (pluggable host, off by default)
- `api/auth.py` validates RS256 JWTs against the issuer's JWKS (PyJWT), checking audience and issuer.
- **Roles:** `viewer` (read), `agent` (case events, intake), `lead` (+ planner and assignment), `analyst` (+ inject/ingest/reset). They come from the token's `permissions` claim or a namespaced roles claim if present, else from `AUTH_ROLE_MAP` (email → role).
- **Enforced per endpoint.** `/api/config` exposes the public OIDC settings, and the SPA uses `@auth0/auth0-spa-js` (MIT) only when auth is on.

### 3.6 Vultr + domain (deploy kit)
- `Dockerfile` (multi-stage: node build, then python slim), `docker-compose.yml` (app + Caddy), `deploy/Caddyfile` (`{$DOMAIN}` gets automatic TLS), `deploy/VULTR.md`.
- The in-app scheduler (`DETECT_INTERVAL_MINUTES`) reruns detection on the live feed.

---

## 4. Order of work
1. UI/UX + corrections (no dependencies)
2. Storage layer + Tiger schema + signal feed (touches every app-table call; tested on embedded Postgres)
3. Assistant + briefs
4. Voice
5. Auth
6. Deploy kit
7. Tests + docs + report

Every step keeps `python -m pytest tests` green and the zero-key demo working.

---

## 5. Status after implementation (Sept 26 2026)

| Item | State | Verified how |
|---|---|---|
| UI/UX: provenance tags, four-question case card, region → queue drill-down, keyboard nav, focus/skip/reduced-motion, role-aware controls | Done | Playwright against the real app in Chrome (light + dark), no console errors |
| Credibility fixes (Replay = scenario, "non-transferred history", "no *recorded* transfers", no "saves" wording) | Done | Screenshots + router reason text |
| Storage layer: SQLite ↔ Postgres, `signal_points` feed, import job, ingest API, hypertable when Timescale is present | Done | 40 tests incl. full pipeline on embedded Postgres. **Not yet run against Tiger Cloud** (needs the team's account) |
| Gemini assistant + cited briefs, offline fallback, caps, cache | Done | Mocked-API tests. **Not yet called with a real key** |
| ElevenLabs customer updates + read-aloud, browser fallback, cache, caps | Done | Mocked-API tests; browser fallback exercised in Chrome. **Not yet called with a real key** |
| Auth: OIDC JWT verification, 4 roles, per-endpoint enforcement, SPA login | Backend done + tested with local RSA keys. **SPA login flow untested** (needs an Auth0 tenant) |
| Vultr/domain deploy kit (Dockerfile, compose, Caddy, entrypoint, scheduler) | Written. **Not built** (no Docker on the dev machine) |
| Hardware, MathemaTech, Solana, Presage | Rejected (§2) | – |
