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

How the voice is chosen: if the server has an ElevenLabs key, the app asks our API for ElevenLabs audio. If that
fails, it says why on screen ("ElevenLabs didn't play…") and, unless `VOICE_BROWSER_FALLBACK=false`, reads the text
with the browser's built-in voice (the Windows voice on Windows). **Hearing the Windows voice = ElevenLabs isn't
configured on the running server, or it returned an error.** The on-screen message tells you which.

**A. Account and credits**
1. Sign in at https://elevenlabs.io.
2. Redeem the Hack the Hill Creator code (Discord → #coupon-codes → Start Redemption → Hack the Hill III), then check
   Subscription shows the Creator plan. On the free plan, ElevenLabs often blocks API calls from VPNs, cloud servers
   and shared networks (`detected_unusual_activity`).

**B. API key (gives `ELEVENLABS_API_KEY`)**
1. Go to **Developers → API Keys → Create API Key** (in some layouts it's the profile menu → API Keys).
2. Name it `northwind-triage`. If you restrict the key, enable at least **Text to Speech** (and **Voices: read** so the
   check command can confirm the voice). Leave the credit limit unset, or set it above your daily cap.
3. Copy the key **when it's shown** (it starts with `sk_` and is shown only once) → `ELEVENLABS_API_KEY`.

**C. Voice (optional, `ELEVENLABS_VOICE_ID`)**
The default `JBFqnCBsd6RMkjVDRZzb` is a standard premade voice. To change it: Voices → pick a voice (add it from the
Voice Library first if needed) → ⋯ → **Copy voice ID**.

**D. `.env`**
```
ELEVENLABS_API_KEY=sk_…
ELEVENLABS_VOICE_ID=JBFqnCBsd6RMkjVDRZzb
ELEVENLABS_MODEL=eleven_flash_v2_5
VOICE_BROWSER_FALLBACK=false      # while testing, so a failure is silent instead of the Windows voice; set true for the demo
```
No quotes and no spaces around `=` are needed.

**E. Check, then restart**
1. `python -m engine.voice_check --save check.mp3`: it shows the key prefix, confirms the voice and plan, and makes
   one real ~20-character call (about 10–20 credits). Play `check.mp3` to hear it. Every line should be ✓.
2. Pull the latest code, run `cd web && npm run build`, then **restart the server**: `.env` is only read at start-up.
3. Reload the page, open a case → Customer update → ▶ Play update. The card says "Voice: ElevenLabs"; if it fails, the
   red message says why.

| Message says | Fix |
|---|---|
| "browser (ElevenLabs not configured on the server)" | The running server has no key: check `.env` is in the repo root and restart the server |
| `invalid_api_key` | Wrong or deleted key. Create a new one and copy the whole `sk_…` value |
| `missing_permissions` | The key is restricted: enable Text to Speech on it |
| `quota_exceeded` | Out of credits: redeem the Creator code |
| `detected_unusual_activity` | Free-plan block on this network: redeem the Creator code or change network |
| `voice_not_found` | Voice ID isn't in this account: copy one from Voices |
| "Can't reach api.elevenlabs.io" | Network, proxy or firewall on the server machine |
| "daily cap reached" (HTTP 429) | Raise `ELEVENLABS_MAX_CHARS_PER_DAY` or wait until tomorrow (UTC) |

Costs: `eleven_flash_v2_5` is about 0.5 credit per character. Requests over 600 characters are refused, the daily
cap is 15,000 characters, and audio is cached in `data/tts_cache/`, so replaying the same update is free.

## 4. Auth0 (login + roles)

You need three things from Auth0: the **tenant domain**, an **API** (its Identifier becomes the audience) and a
**Single Page Application** (its Client ID). Dashboard: https://manage.auth0.com.

**A. The API (gives `AUTH_AUDIENCE`)**
1. Applications → **APIs** → **+ Create API**.
2. Name: `Northwind Triage API`. Identifier: `https://api.northwind-triage` (any URL-shaped string; it is never called,
   but it can't be changed later). Signing algorithm: **RS256** → Create.
3. On the API's **Settings** tab, turn on **Allow Offline Access** (lets the app stay signed in across refreshes) → Save.
4. Copy the **Identifier** exactly → `AUTH_AUDIENCE`.

**B. The application (gives `AUTH_DOMAIN` and `AUTH_CLIENT_ID`)**
1. Applications → **Applications** → **+ Create Application** → Name `Northwind Triage` → type **Single Page Web
   Applications** → Create. (A "Regular Web Application" won't work: the browser can't exchange the login code.)
2. On its **Settings** tab, copy:
   - **Domain** (e.g. `dev-abc123.us.auth0.com`) → `AUTH_DOMAIN`. Just the host: no `https://`, no trailing `/`.
   - **Client ID** → `AUTH_CLIENT_ID`. The Client Secret is **not** needed; leave it out of `.env`.
3. Scroll to **Application URIs** and enter the address you open the app at, **exactly** (scheme, host and port; no
   trailing slash), in all three boxes, comma-separated if more than one:
   - Allowed Callback URLs: `http://localhost:8000`
   - Allowed Logout URLs: `http://localhost:8000`
   - Allowed Web Origins: `http://localhost:8000`

   Add `http://localhost:5173` too if you use `npm run dev`, and `https://your.domain` once deployed.
   `http://127.0.0.1:8000` is a *different* address from `http://localhost:8000`.
4. If there's a **Refresh Token Rotation** section, turn rotation on. Click **Save Changes** at the bottom.
5. **Connections** tab: make sure **Username-Password-Authentication** is enabled.

**C. A login for the demo**
1. User Management → **Users** → **+ Create User** → an email and password, connection Username-Password-Authentication.
2. Open the user and copy its **user_id** (e.g. `auth0|66f1c0ffee…`).

**D. `.env`**
```
AUTH_ENABLED=true
AUTH_DOMAIN=dev-abc123.us.auth0.com
AUTH_CLIENT_ID=<Client ID from B.2>
AUTH_AUDIENCE=https://api.northwind-triage
AUTH_ROLE_MAP=auth0|66f1c0ffee…:analyst
AUTH_DEFAULT_ROLE=viewer
```
Roles are `viewer`, `agent`, `lead` and `analyst` (analyst can do everything, including Inject scenario and Reset).
Map several users with commas: `auth0|aaa:analyst,auth0|bbb:agent`. Anyone not listed gets `AUTH_DEFAULT_ROLE`.
Mapping by email instead of `user_id` needs an Auth0 Post-Login Action that adds the email to the access token:
`api.accessToken.setCustomClaim('https://northwind-triage/email', event.user.email)`.
Leave `AUTH_ROLES_CLAIM` at its default.

**E. Check, then start**
1. `python -m api.auth_check`: it checks the values, confirms the tenant exists, and asks Auth0 whether it accepts the login
   request from `http://localhost:8000` (add your deployed URL as an argument). Every line should show ✓.
2. Rebuild the UI if you pulled new code (`cd web && npm run build`), then **restart the server**: `.env` is only read at
   start-up. The server refuses to start if a required auth value is missing.
3. Open `http://localhost:8000` (the same address you registered), sign in, and check the top bar shows your name · analyst.

**If you see Auth0's "Oops!, something went wrong" page:** click **See details for this error**.
| Details say | Fix |
|---|---|
| Unknown client / invalid client_id | `AUTH_CLIENT_ID` is wrong, or the app lives in a different tenant from `AUTH_DOMAIN` |
| Callback URL mismatch | The address in the browser isn't in Allowed Callback URLs exactly (port, `localhost` vs `127.0.0.1`, trailing slash) |
| Service not found | `AUTH_AUDIENCE` doesn't match the API Identifier character for character |

Errors Auth0 sends back to the app (for example "Service not found", or the API rejecting the token) are shown on the
app's own sign-in screen with a hint.

## 5. Vultr + domain
1. Create a Cloud Compute instance (1 vCPU / 1 GB, ~$5/month) with Docker (Marketplace "Docker" image or
   `curl -fsSL https://get.docker.com | sh`). Open ports 80 and 443.
2. `git clone` the repo, add `.env` (set `DOMAIN=your.domain`, `DETECT_INTERVAL_MINUTES=15` for the scheduled detector),
   then `docker compose up -d --build`.
3. Domain (GoDaddy Registry): add an A record pointing to the instance IP. Caddy fetches a TLS certificate automatically.
4. If using Auth0, add `https://your.domain` to the SPA's allowed URLs.

The Docker files were written but **not built on the development machine** (it has no Docker). The first real
build is on the Vultr box; the app itself is tested locally.
