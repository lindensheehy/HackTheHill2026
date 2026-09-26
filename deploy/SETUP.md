# Setting up the sponsor services

Every service is optional. Start with nothing (FOSS mode), then add them one at a time; the app tells you in
`/api/config` and in the UI which ones are live. Put values in `.env` (copy `.env.example`).

## 1. Tiger Data (storage + time-series feed)
1. Create a service on Tiger Cloud (free plan is enough: our data is well under 50 MB).
2. Copy the connection string into `DATABASE_URL` (keep `?sslmode=require`).
3. Import and build: `python -m jobs.rebuild --import`. This copies the 6 source tables with COPY, builds the
   baselines, and writes the signal feed into `signal_points`, which becomes a hypertable because TimescaleDB is present.
4. Check it: `GET /api/signals` should report `"backend": "postgres", "timescale": true, "host": "Tiger Cloud"`.
5. Live feed demo:
   `curl -X POST $URL/api/signals -H 'Content-Type: application/json' -d '[{"region":"Fenwick","month":"2026-10","signal":"complaints:Other","value":400}]'`.
   Detection reruns and returns the new active alerts. `DELETE /api/signals` removes the ingested points.

Only Apache-2 TimescaleDB features are used (hypertables). A self-hosted PostgreSQL works identically (plain table).

## 2. Gemini (assistant + briefs)
1. Get an API key in Google AI Studio, then set `GEMINI_API_KEY`.
2. `GEMINI_MODEL` defaults to `gemini-3.1-flash-lite` (the cheapest stable Flash-Lite as of Sept 2026; check the
   model list if the call fails). Calls use minimal thinking and ≤ 700 output tokens, and are capped at
   `GEMINI_MAX_CALLS_PER_DAY` (300).
3. Check it: the assistant header says "Gemini (model)", and briefs show the "AI-generated" tag.

## 3. ElevenLabs (spoken customer updates)
1. Redeem the Hack the Hill Creator-tier code, then create an API key and set `ELEVENLABS_API_KEY`.
2. Defaults: `eleven_flash_v2_5` (~0.5 credit/char), voice `JBFqnCBsd6RMkjVDRZzb`, `mp3_22050_32`.
   Requests over 600 characters are refused, the daily cap is 15,000 characters, and audio is cached in
   `data/tts_cache/`, so replaying the same update is free.
3. Check it: the case drawer's Customer update card says "Voice: ElevenLabs".

## 4. Auth0 (login + roles)
1. Create an **API**: identifier, e.g. `https://api.northwind-triage` → `AUTH_AUDIENCE`. Signing algorithm RS256.
   Optional: enable RBAC plus "Add Permissions in the Access Token", and define the permissions `cases:write`,
   `intake:create`, `cases:assign`, `alerts:simulate`, `signals:write`, `demo:reset`.
2. Create a **Single Page Application**. Allowed Callback, Logout and Web Origins = your site URL
   (`http://localhost:8000` locally). Client ID → `AUTH_CLIENT_ID`. Tenant domain → `AUTH_DOMAIN`.
3. Roles without paid features: set `AUTH_ROLE_MAP=judge@x.com:analyst,agent@x.com:agent`. Access tokens only carry
   `email` if an Auth0 Action adds it. The simplest option is a Post-Login Action:
   `api.accessToken.setCustomClaim('https://northwind-triage/email', event.user.email)`.
   Alternatively, map by `sub` (`auth0|abc123:lead`).
4. Set `AUTH_ENABLED=true`. For judges, create a demo user with the analyst role and put its credentials in the Devpost notes.

## 5. Vultr + domain
1. Create a Cloud Compute instance (1 vCPU / 1 GB, ~$5/month) with Docker (Marketplace "Docker" image or
   `curl -fsSL https://get.docker.com | sh`). Open ports 80 and 443.
2. `git clone` the repo, add `.env` (set `DOMAIN=your.domain`, `DETECT_INTERVAL_MINUTES=15` for the scheduled detector),
   then `docker compose up -d --build`.
3. Domain (GoDaddy Registry): add an A record pointing to the instance IP. Caddy fetches a TLS certificate automatically.
4. If using Auth0, add `https://your.domain` to the SPA's allowed URLs.

The Docker files were written but **not built on the development machine** (it has no Docker). The first real
build is on the Vultr box; the app itself is tested locally.
