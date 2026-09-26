# Web front end (`web/`)

Vite 5 + React 18, plain JSX. Deps: recharts 2, @xyflow/react 12. `vite.config.js` proxies `/api` → 127.0.0.1:8000.
`npm run build` → `web/dist` (served by FastAPI). A bundle-size warning (~800 kB) is expected and harmless.

## Boot and session (`App.jsx`, `auth.js`, `session.js`)
- `/api/config` → `initAuth(config.auth)`. If auth is on and the user isn't logged in, show the `<Login>` screen. Otherwise `/api/me` → `<Shell>`.
- `Session` context: {config, user, can(perm), focus, setFocus}. `focus` = {case_id} while the drawer is open, or {alert_id} while an investigation shows; it's sent to the assistant. It resets on tab change.
- The topbar shows name · role and Sign out when auth is on; Reset appears only with demo:reset. The floating `<Assistant page>` is on every tab.

## Routing (hash-based, `App.jsx`)
- `#/dashboard[/<alertId>]`: Operations; the optional id preselects an alert.
- `#/intake`
- `#/replay`
- `#/queue[/<NW-id> | /auto | /planner][?region=&priority=&category=&owner=&system=&search=]`: an NW-id highlights and scrolls to the row and opens its drawer; query params pre-set the filters (the region cards link here). `go(tab, arg, params)` is exported.

Topbar:
- Tabs, with a red badge showing the active-alert count on Operations; "Data as of".
- Theme button cycles Auto→Dark→Light (localStorage `nw-theme`, in try/catch; sets `data-theme` on `<html>`).
- Reset button: confirm → POST /api/demo/reset → reload.

## Files
| File | Role |
|---|---|
| api.js | `api.*` wrappers for every endpoint; attaches the bearer token; throws ApiError(status, detail); `blob()` for audio |
| auth.js | Optional Auth0 SPA client: initAuth, token, login, logout |
| speech.js | speak(text, {provider, fetchAudio, onEnd}): ElevenLabs blob or browser speechSynthesis fallback; stopSpeaking; listen() via SpeechRecognition |
| components/Assistant.jsx | Floating "Ask Northwind" panel: suggestions per page, history, mic input, 🔊 per answer (ElevenLabs if ≤ 600 chars, else browser), citation chips expand the evidence with its provenance, mode tag (AI-generated / Evidence lookup) |
| components/CustomerUpdate.jsx | Drawer card: transcript, ▶ Play update, "I still need help" (customer_help event → escalates), voice provider label; refetches when the case changes |
| format.js | pct, int, num, gbp (£, k/M compaction), compact, monthLabel ("Sep 26"), fmt(v, kind) |
| components/common.jsx | Card, Provenance (observed / policy / assumption / simulated / ai / template: glyph + text tag), Loading, Pri (priority pill), Overdue (dot + "Nd over/left", colour from overdue_state), Tip (tooltip body), Sparkline (SVG), Legend, axisProps |
| components/TriageCard.jsx | Renders a TriageResult: owner block (policy tag), alert callout, "Legacy route vs non-transferred history" table (columns Legacy / Not transferred; observed tag; an "if routing avoids the transfer… based on history" line), likely resolution bars, info-only chip (highlighted ≥ 45%), reasons. `compact` stacks it for the drawer |
| views/Dashboard.jsx | Hero (£2.4M/quarter + narrative), 5 KPI tiles, SlaChart (breach line + 3-month rolling, shaded incomplete months; separate opened/closed bars, synced), TransferPanel (paired bars with ×multipliers, entry-system rates, callout), RegionGrid (6 cards, focus regions outlined orange, links "Open complaints (N) →" and "P1 only" to `#/queue?region=…`), Alerts, SystemGraph, Heatmap, RouterImpact (80%×60%, assumption tag, "Not a measured effect"), InfoOnly (#4), SmartMeter (#6, assumption tag). The transfer callout says CaseTrack has no *recorded* transfers |
| views/Alerts.jsx | FeedBadge (points per source + where stored: SQLite / Postgres / Tiger Cloud · hypertable). Brief (Generate → three cited sections, AI or template tag, evidence list, Regenerate for Gemini). Feed (active by default; history toggle), Inject/Clear simulation (analyst only), auto-selects the strongest active alert; Investigation: spike line chart (last 12 months, red reference line at the alert month), per-region table, shared-system notes, linked open complaints (click → queue) |
| views/SystemGraph.jsx | React Flow with a fixed POS layout: entry systems (x=0), CaseTrack + regions (x=260), serving systems (x=520). Edges are always drawn left→right (flipped when needed); transfers_to edges are animated orange with a rate label. Alert nodes are red. Clicking a node shows system info |
| views/SmartMeter.jsx | Sliders: exception cost (default £34, "upper bound"), rollout 2–5 years (default 4), coverage (default 30%). 12-year cumulative cost vs benefit with a payback line; scatter of penetration vs estimated reads |
| views/Intake.jsx | Form (channel, entry-system override, category, priority, region, account) + prepared examples → POST /api/triage → callout with queue rank or auto lane, link to it, TriageCard |
| views/Replay.jsx | Plays at 1 month/sec via requestAnimationFrame over weeks; adoption/avoidance sliders (0.8/0.6); an "assumption-based scenario" banner; annualised tile ("real transfers × assumed avoided"); 5 counters; cumulative transfers area chart ("What happened" vs "Scenario: with the router", 500-step ticks); ticker of sampled router decisions |
| views/Queue.jsx | Keyboard (window listener, off while typing or with the drawer open): / j k ↑ ↓ Enter ?; cursor row outlined. Drawer starts with the four-question card (What happened / What happens next / Who owns it / What's blocking it, each with a provenance tag), then Why #N in the full queue, Actions (disabled with a tooltip when the role lacks the permission), CustomerUpdate, alert, history, TriageCard. Sub-tabs Queue / Auto-answer lane / Backlog planner. QueueTable fetches all rows (limit 2000) and pages 100 client-side; filters refetch; strict toggle; summary tiles incl. the stored-flag 98% contrast. CaseDrawer: "Why is this case #N", actions (owner select, In progress/Escalate/Resolve, note), event log, linked alert, account timeline, TriageCard. AutoLane: table + "Customer came back" (auto_bounce event) + bounced list |
| views/Planner.jsx | Inputs: inflow, assumed FTE, extra agents (default 5), clear target (600), router checkbox. Chart: today / +extra / +extra+router over 24 months; clearance month |

## Credibility labelling (UI/UX)
- Every panel making a claim carries a `<Provenance>` tag. The Replay has an "assumption-based scenario" banner and its series is "Scenario: with the router".
- The TriageCard compares "Legacy" with "Not transferred" history ("an expectation, not a guarantee"). The transfer callout says CaseTrack has no *recorded* transfers.
- Region cards link to `#/queue?region=…` (and P1 only). Accessibility: skip link, `:focus-visible` rings, aria labels and roles on dialogs and tabs, reduced-motion support, and status always as text plus glyph, never colour alone.

## Client-side formulas
- **Planner:**
  - per_agent = closures / fte
  - speedup = effort(s) / effort(s·(1 − 0.8·0.6)), where effort(x) = (1−x)·68 + x·121 (≈ +11.2%)
  - backlog_{t+1} = max(0, b + inflow − (fte+extra)·per_agent·(router ? speedup : 1)); "cleared" = first month with b ≤ target
- **Smart meter:**
  - meters = 519k·coverage; capex = meters·148; benefitShare = min(1, coverage/0.3)
  - annual = (complaints_avoided·68 + excess_bill_correction + exceptions_avoided·excCost)·benefitShare
  - Spend is linear over the rollout years; benefit ramps with installation; payback = first year where cumulative benefit ≥ cost
- **Replay:** avoided = cumulative transfers × adoption × avoidance; the £/days/reopens/breaches counters = avoided × per_avoided.

## Design system (styles.css; follows the dataviz skill's reference palette)
- Tokens live on `:root`. Dark mode is declared twice: `@media (prefers-color-scheme: dark) :root:not([data-theme="light"])` and `:root[data-theme="dark"]`.
- Semantic colour use:
  - `--s1` blue = routed / not transferred / closed / primary; `--s2` orange = legacy / transferred / opened / focus regions; `--s3` aqua = 3rd series; `--s7` violet = "simulated" tag.
  - Status: `--good`, `--warning`, `--serious`, `--critical` (red = past SLA / alerts). They are reserved and never used as series colours.
  - Sequential blue ramp `--seq-100..700` for heatmap and meters (inverted in dark mode).
- Rules to keep:
  - no dual y-axes (use stacked charts sharing an x, with `syncId`);
  - text uses ink tokens (`--ink`, `--ink-2`, `--muted`), never series colours;
  - a legend for ≥ 2 series; Recharts `isAnimationActive={false}`; bars `maxBarSize` 10 with `radius [4,4,0,0]`; lines 2px; dots r 4 with a surface-coloured stroke;
  - tooltips use `<Tip>`;
  - system-ui font; `.tnum` only for aligned numeric columns.
- Layout classes: `.grid .g2 .g3 .g5 .g-7-5 .g-5-7 .g-side` (all collapse at ≤1100/≤700px; `.grid > * {min-width:0}`), `.stack`, `.row`, `.card`, `.callout(.info)`, `.chip`, `.pri`, `.od`, `.drawer`.
- Never put `gridTemplateColumns` inline: it defeats the responsive breakpoints.
- Verified by headless-Chrome screenshots at 1440px and 500px. Headless Chrome enforces a minimum width of about 500px, so 390px captures look cropped; that's not a bug.
