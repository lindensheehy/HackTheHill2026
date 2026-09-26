# TODO: what is still stubbed, mocked or unverified

Status as of 26 Sept 2026. Everything below is known and deliberate unless marked as a bug. Background:
[plan_integrations.md](plan_integrations.md) (decisions), [deploy/SETUP.md](deploy/SETUP.md) (service setup),
[docs/](docs/README.md) (specs).

## 1. Before the demo (team actions: need accounts, keys or decisions)
- [ ] **Decide on Best FOSS.** Enter it only with the honest statement from plan_integrations.md §1.2. Risk: a judge may treat the hosted Tiger Cloud database as proprietary core.
- [ ] **Recheck pricing and free tiers** (Gemini, ElevenLabs, Tiger, Vultr, Auth0) on submission day; figures were checked 26 Sept 2026.
- [ ] **Gemini:** create a key, set `GEMINI_API_KEY`, ask one question and generate one brief. Confirm `gemini-3.1-flash-lite` is still listed (2.5 Flash-Lite retires on 16 Oct 2026).
- [ ] **ElevenLabs:** redeem the Creator code, set `ELEVENLABS_API_KEY`, play one customer update. Confirm the voice and model IDs work.
- [ ] **Tiger Data:** create a service, set `DATABASE_URL`, run `python -m jobs.rebuild --import`, check that `/api/signals` reports `timescale: true, host: Tiger Cloud`, then run the curl ingest example.
- [ ] **Auth0:** create the tenant, API and SPA; add an Action for the email claim or map roles by `sub`; create an analyst demo login for judges and put it in the Devpost notes.
- [ ] **Vultr + domain:** create the instance, `docker compose up -d --build`, point the DNS A record, check that HTTPS works, and add the URL to Auth0.
- [ ] Before presenting, press **Reset**. Don't run `pytest` against the live demo store (see §4).
- [ ] Tick the Devpost boxes: UI/UX, FOSS (if decided), ElevenLabs, Gemini, Tiger Data, Auth0, Vultr, GoDaddy domain.

## 2. Built, but only tested against fakes (verify on first real run)
| Integration | What's tested | What's not | Where |
|---|---|---|---|
| Gemini | Request shape, citation filtering, budget cap, failure fallback (all mocked) | A real `generateContent` call. That `thinkingConfig.thinkingLevel: "minimal"` is accepted (there's a retry without it on HTTP 400). Real JSON-mode output quality for briefs | engine/assistant.py |
| ElevenLabs | Request body, caching, per-request and daily caps (mocked) | A real TTS call; whether `eleven_flash_v2_5` and voice `JBFqnCBsd6RMkjVDRZzb` are valid for the account | engine/voice.py |
| Tiger Cloud | Full pipeline on embedded Postgres **without** TimescaleDB | Hypertable creation on a real service; COPY import speed and TLS; per-thread connections under remote latency; the `store.info()` host check (it looks for `tsdb.cloud` in the URL) | engine/store.py, jobs/import_source.py |
| Auth0 | Server-side JWT verification and roles with locally generated keys | The SPA login redirect, the silent token refresh, logout, and the real JWKS fetch | web/src/auth.js, api/auth.py |
| Docker / Vultr / Caddy | Nothing (no Docker on the dev machine) | Image build, entrypoint rebuild at start-up, TLS, the scheduled detector (`DETECT_INTERVAL_MINUTES`) | Dockerfile, docker-compose.yml, deploy/ |
| Browser voice input | Button is hidden where unsupported | Microphone flow (Chrome/Edge SpeechRecognition) never exercised | web/src/speech.js |

## 3. Stubs and simulations inside the product (say so in the demo)
- **Auto-answer lane (#4):** no message is actually sent. `auto_template` is just a template *name*, and there is no delivery channel (email/SMS/portal). "Customer came back" is an agent-side button simulating a reply.
- **Customer update (ElevenLabs):** in-app playback only; no outbound call, SMS or email. "I still need help" is pressed by the agent on the customer's behalf. Templates are ours, not Northwind-approved wording.
- **Alert scenario:** the October month is synthetic (tagged Simulated everywhere).
- **Live feed:** `POST /api/signals` exists, but nothing real feeds it; it's demonstrated by hand with curl.
- **Replay and dashboard "#1 Route at intake" tile:** an assumption-based scenario (adoption × avoidance sliders), not a measured effect of routing.
- **Owner policy and team names** (router `TEAMS`/`TEAM_SYSTEMS`): proposed by us; the data has no destination-system field.
- **Channel → entry-system defaults** (`CHANNEL_ENTRY`): assumed when intake doesn't say where a complaint arrived.
- **Backlog planner:** the 60-FTE headcount is an assumption, and "effort ∝ Finance cost (£68 vs £121)" is a modelling assumption.
- **Smart-meter projection:** the exception-handling cost is unknown (the slider defaults to the £34 upper bound); "benefit arrives by ~30% coverage" is a hypothesis from synthetic data.
- **Intake complaints** get a synthetic account ID (`ACC-9xxxxx`) when none is entered, and are always dated as of 2026-09-30.
- **Case actions:** no assignment to individual agents, no locking or concurrency control, no SLA pause/hold states.

## 4. Known technical debt
- [ ] `tests/test_baselines_alerts.py` runs against the real app store and calls `reset_scenario()`, which wipes a live demo's simulated alerts. It should move to a temporary store like test_integrations.
- [ ] FastAPI `@app.on_event("startup")` is deprecated; move it to a lifespan handler.
- [ ] Front-end bundle is ~800 kB. Code-split Recharts, React Flow and Auth0 (the auth SDK is already dynamically imported).
- [ ] `/api/dashboard` and `/api/replay` are cached per process, so the server must restart after `jobs.rebuild`. Add cache invalidation.
- [ ] The queue recomputes scores for every open case on each request (~0.25 s locally; slower over a remote DB). Cache it per request burst, or invalidate on events.
- [ ] Postgres uses one connection per thread with no pool (psycopg_pool would add a dependency). Reconsider if Tiger latency hurts.
- [ ] Cost caps are global per day, not per user; the assistant has no per-user rate limit. CORS is `*`.
- [ ] `data/tts_cache/` and the `ai_briefs` table grow without eviction (tiny at demo scale).
- [ ] Usage "day" is UTC wall-clock, while the app's data date is fixed at 2026-09-30 (intentional, but easy to confuse).
- [ ] Mobile/phone-width layout was checked before the assistant panel, customer-update card and four-question card were added. Re-check at 390–500 px.
- [ ] Accessibility has not been audited with a screen reader; only focus rings, aria labels, the skip link and reduced motion are in place.
- [ ] The `routed` key in the TriageResult JSON now means "non-transferred history". Rename it (breaking API change) if there's time.

## 5. Deliberately not built
- Gradient-boosted expected-days model (plan.md P2 stretch).
- #5 unified case-history integration layer (dropped in plan.md §8).
- Streamlit fallback (the React UI exists).
- Hardware, MathemaTech, Solana and Presage challenges (rejected, with reasons, in plan_integrations.md §2).
