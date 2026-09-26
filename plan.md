# Northwind Complaint Triage: Project Plan

## 1. The pitch in one breath

Northwind's complaint handling has been getting worse for two years. Monthly volume is up 37%, time to close has gone from 9 to 38 days, SLA breaches from 44% to about 92%, and the regulator score from 4.3 to 2.6, with **£2.4M per quarter** in penalty exposure. The largest cause we can fix is **transfers between systems**: a transferred complaint takes 15 days longer, costs £53 more, and is **3x more likely to reopen**.

We built a triage platform that:
1. **Routes every complaint to the right owner the moment it arrives**, so it doesn't bounce between systems (Routing Engine).
2. **Shows leadership what is going wrong and where**, and connects complaint trends to the operational systems behind them (Operations Dashboard).
3. **Gives agents a live, ranked work queue**, so the most overdue, highest-priority cases are handled first (Triage Queue).

And we use the same data to argue for two things Northwind should do next: **resolve information-only complaints automatically** and **redirect smart-meter spending to the two regions that need it**.

It uses simple, explainable statistics, not an LLM. Northwind already paid £640k a year for an AI assistant pilot that got worse every month and was paused.

---

## 2. Scope at a glance

| # | Component | Role in the pitch | What we build |
|---|---|---|---|
| 1 | Intake Routing Engine | Core technical story: the transfer problem | Backend engine + two demo surfaces (Intake Simulator, Replay) |
| 3 | Operations Dashboard | Main visual for judges | Web dashboard; depth scales with available time |
| 2 | Triage Queue | User-facing app that brings 1 and 3 together | Ranked queue of pending complaints + case detail + backlog planner |
| 4 | Auto-resolution of information-only complaints | Talking point | Nothing, or at most a stubbed "auto-resolved" lane in the queue |
| 6 | Smart-meter investment case | Talking point, backed by numbers | Numbers in the slides; a projection chart in the dashboard if time allows |
| 5 | Unified case-history integration layer | **Dropped** | Out of scope and too heavy technically. #1 captures much of its value (see §8) |

---

## 3. What the data tells us (evidence for the pitch)

All figures come from `data/data.db`. Open tickets are excluded from resolution metrics unless stated.

**Transfers**
- About 34% of closed complaints were transferred between systems.
- Transferred vs not: **38.2 vs 23.0 mean days**, **87.7% vs 69.0% SLA breach**, **29.2% vs 8.9% reopen**.
- Cost per complaint: **£121 transferred vs £68** (Finance cost model FY26).
- Every one of the slowest 1% of complaints (>85 days) was a transfer.
- **Complaints that start in CaseTrack (SYS-04) are never transferred.** Complaints that start anywhere else are transferred about **46% of the time, whatever their category, channel, priority or region** (all fall between 44% and 49%).
  → Transfers aren't caused by hard complaints. They're caused by **where the complaint enters the system**. That's why routing at intake is the fix.
- Last 12 months: **4,795 transfers**. That's about £254k in extra handling, about 73k extra complaint-days, and about 975 extra reopens.

**SLA and priority**
- Every SLA tier (5, 10 and 20 days) finishes at **about 1.7x its target**.
- Breach rates barely differ by priority: P1 72%, P2 75%, P3 76%. Priority sets the deadline but doesn't get cases worked any faster relative to it.

**Backlog**
- 1,599 complaints are open: 35 P1, 219 P2, 1,345 P3.
- **Data caveat:** the stored `sla_breach` flag marks 98% of open tickets as breached. Measured from `date_opened` to 30 Sep 2026 (the last day in the data), the median open ticket is only **1 day** past SLA, 25% are still at least 8 days inside it, and the worst is 106 days over. **The queue must calculate overdue days from dates, not trust the stored flag.**
- Recent months: about 1,200 complaints opened vs about 1,160 closed per month, so the backlog is still growing.

**Information-only complaints**
- 24% of closed complaints could have been resolved with information alone, about 3,000 a year.
- By category it's very uneven: Other 61%, Service - poor communication 53%, Water 33%, Metering - no read taken 11%.
- They reopen no more often than other complaints (16.2% vs 15.7%), so answering with information works.

**Metering: Barrowdale and Dunmoor**

| Measure | Barrowdale + Dunmoor | Other four regions |
|---|---|---|
| Accounts | 519k | 1.28M |
| Smart meter penetration | 0% | 30% → 81% over the two years |
| Estimated read rate | ~62% | ~22% |
| Billing exceptions per 1k accounts per month | ~25 | ~8.5 |
| Billing/metering complaints per 1k accounts (last 12 months) | 6.7 | 4.0 |
| Share of bill-correction value | 46% (from 2 of 6 regions) | 54% |

- Both regions run on Aurora Billing (SYS-01, COBOL, two developers left) and MeterHub (SYS-06), whose estimation algorithm hasn't changed since 2012.

---

## 4. Architecture

```
                     ┌──────────────────────── data/data.db (SQLite) ────────────────────────┐
                     │ source tables (from CSVs)          │ app tables (created by us)       │
                     │ northwind_complaints, meter_reads, │ triage_results, case_events,     │
                     │ systems, unit_costs, kpis, pilot   │ alerts, baselines                │
                     └───────────────┬────────────────────┴──────────────┬───────────────────┘
                                     │                                   │
                        ┌────────────▼────────────┐        ┌─────────────▼─────────────┐
                        │ engine/ (Python)        │        │ jobs/ (Python)            │
                        │  build_baselines.py     │        │  detect_alerts.py         │
                        │  router.py  (#1)        │        │  (early warning, #3)      │
                        │  queue_score.py (#2)    │        └─────────────┬─────────────┘
                        └────────────┬────────────┘                      │
                                     └──────────────┬────────────────────┘
                                          ┌─────────▼─────────┐
                                          │ api/ (FastAPI)    │
                                          └─────────┬─────────┘
                                          ┌─────────▼─────────────────────────────────┐
                                          │ web/ (React + Vite)                       │
                                          │  Dashboard (#3) │ Queue (#2) │ Intake (#1) │
                                          └───────────────────────────────────────────┘
```

**Stack recommendation:** FastAPI + pandas on the backend, since it reuses what we've already written. React + Vite + Recharts on the front end, with React Flow for the system dependency graph. **Fallback:** if front-end time runs short, the same three views work as Streamlit pages over the same `engine/` modules. That looks less polished but is much faster to build.

**Principles**
- Source tables are read-only. Everything we generate goes into separate app tables, rebuildable by a script.
- Fix the "as of" date at **2026-09-30** (the last day in the data), so ages, overdue days and alerts are consistent in the demo.
- Every score shown in the UI has a plain-English reason next to it (e.g. "complaints entering via CallCentre One are transferred 46% of the time"). Judges and agents should never see an unexplained number.

**Suggested folder layout** (alongside the existing `analysis/`, `data/`, `database_migration/`):
```
engine/   baselines, router, queue scoring, cost model
jobs/     alert detection, table rebuilds
api/      FastAPI app
web/      React front end
```

---

## 5. Component 1: Intake Routing Engine

### 5.1 Problem it solves
A complaint's route is decided by where it happens to enter: phone CRM, web self-service, billing or the case system. From outside the case system, about 46% get transferred, and transfer history gets lost on the way. The engine makes the routing decision **once, at intake**, and creates the case with its owner, expected resolution path and risk already attached.

### 5.2 Inputs (only what's known when the complaint arrives)
- From the complaint: `channel`, `category`, `priority`, `region`, `account_id`, `date_opened`, entry system.
- Joined context:
  - that region's meter signals for the month (`estimated_read_rate`, `smart_meter_penetration`, billing exceptions per 1k accounts);
  - the systems serving the region (from `northwind_meter_reads.systems_serving_region` + `northwind_systems`);
  - the account's prior complaints;
  - any active alert for that region and category (from #3).
- **Never used as inputs (outcome leakage):** `days_to_close`, `date_closed`, `sla_breach`, `reopened`, `resolution_action`, `bill_correction_value`.

### 5.3 Outputs: the `TriageResult`
```json
{
  "complaint_id": "NW-126001",
  "owner": { "system": "SYS-04 CaseTrack", "team": "Billing Resolution" },
  "legacy_route": { "entry_system": "SYS-05 CallCentre One", "transfer_risk": 0.46 },
  "resolution_path": [
    { "action": "Bill corrected and re-issued", "share": 0.53, "median_days": 21, "reopen_rate": 0.16 },
    { "action": "Refund or credit applied",     "share": 0.24, "median_days": 22, "reopen_rate": 0.17 },
    { "action": "Information provided only",    "share": 0.13, "median_days": 19, "reopen_rate": 0.16 }
  ],
  "info_only_likelihood": 0.23,
  "expected_days": { "routed": 21, "legacy": 27 },
  "breach_risk":   { "routed": 0.69, "legacy": 0.77 },
  "context": {
    "region_alert": "Estimated-read complaints elevated in Barrowdale (z = 2.4)",
    "region_systems": ["SYS-01 Aurora Billing", "SYS-06 MeterHub"],
    "account_prior_complaints": 1
  },
  "queue_score": 0.0,
  "reasons": ["Category 'Billing - disputed amount' resolves in Billing Resolution 100% of the time", "..."]
}
```
The example numbers are illustrative; the real ones come from the baseline tables.

### 5.4 How it works
The honest headline: **transfers can't be predicted from complaint attributes**, because they're flat at about 46% outside CaseTrack. A machine-learning transfer model would learn nothing useful. The value comes from a **deterministic routing policy** backed by **learned lookup tables**:

1. **Owner assignment (rules).** Every complaint gets its case created in the case-owning system at intake, with the resolving team taken from category. The mapping comes from data: each category has a small, fixed set of resolution actions (e.g. "Billing - disputed amount" → bill correction, refund, explanation). The teams are ours to name.
2. **Resolution path (learned).** For each (category, priority), the historical distribution of `resolution_action`, with median days and reopen rate for each action. Uses non-transferred closed cases, weighted towards the last 6 months.
3. **Info-only likelihood (learned).** Historical rate by (category, channel), with smoothing so small groups fall back towards the category rate.
4. **Expected days and breach risk (learned).** Computed separately for **transferred** and **non-transferred** histories of the same (category, priority). This gives the "legacy vs routed" comparison shown on every triage card.
5. **Context enrichment.** Region meter signals, active alerts, account history (reusing `analysis/complaint_histories.py`).

All of these are small SQL/pandas aggregates, precomputed into a `baselines` table by `engine/build_baselines.py`. They're instant to query and easy to explain.

**Stretch:** a gradient-boosted model for expected days (scikit-learn; not installed yet) with a time-based train/test split: train Oct 2024–Mar 2026, test Apr–Sep 2026. Only worth adding if it clearly beats the lookup tables, and we report the comparison either way.

### 5.5 Demo surfaces
The engine runs in the backend, so it needs something visible:

**A. Intake Simulator (live, interactive)**
- A form that looks like an agent's intake screen: channel, category, priority, region, account.
- Submitting shows the triage card: owner, top 3 resolution paths, info-only likelihood, and a **side-by-side "legacy route vs routed" comparison** of expected days, breach risk and cost.
- Include 2–3 prepared examples to click through. One should be a Barrowdale estimated-read complaint that picks up the regional alert from #3.

**B. Replay (the "what if we'd had this" moment)**
- Replays the last 6 months of real complaints (Apr–Sep 2026, about 7,100) through the router at high speed, e.g. one month per second.
- Running counters: transfers avoided, complaint-days saved, reopens avoided, £ saved.
- Sliders for the assumptions: **adoption %** (share of complaints entering through the router) and **transfer avoidance %** (share of would-be transfers the router prevents). Default to conservative values, e.g. 80% and 60%.
- Formulas, per would-be transfer avoided:
  - £ saved = £121 − £68 = **£53**
  - days saved = 38.2 − 23.0 = **15.2**
  - reopens avoided = 0.292 − 0.089 = **0.203**
  - breaches avoided = 0.877 − 0.690 = **0.187**
- Annualised at 100%/100% (upper bound): **about £254k, 73k complaint-days, 975 reopens and 900 breaches avoided per year**. The slide should quote the conservative-slider figures, not the upper bound.

### 5.6 Deliverables and acceptance
- [ ] `engine/build_baselines.py` creates and fills the `baselines` table
- [ ] `engine/router.py`: `route(intake) -> TriageResult`, pure function, unit-tested on 3–5 fixture complaints
- [ ] `POST /triage` and `POST /replay` (streamed or paged) in the API
- [ ] Intake Simulator view and Replay view
- [ ] `engine/cost_model.py`: single source of truth for unit costs (read from `northwind_unit_costs`), used by Replay and the dashboard

---

## 6. Component 3: Operations Dashboard

### 6.1 Purpose
One screen that tells a Northwind executive **how bad it is, where it's worst, why, and what's changing**. It's the judges' first impression, so visual quality matters, but every panel must answer a question.

### 6.2 Panels, in build order (MVP → Target → Stretch)

**MVP**
1. **KPI header:** complaints this month, average days to close, SLA breach rate, first-contact resolution, regulator score. Each shows a sparkline and the change vs 12 months ago. Source: `northwind_monthly_kpis` + complaints.
2. **SLA degradation chart:** monthly breach rate with the 3-month rolling line, plus opened vs closed bars. Recent months are marked as incomplete, because tickets opened then may still be open.
3. **Transfer penalty panel:** transferred vs not, compared on days, breach, reopen and cost. This is the chart that sets up the router pitch.
4. **Region grid:** six region cards showing breach rate, complaints per 1k accounts, estimated read rate, smart meter %, and their systems. Barrowdale and Dunmoor should stand out.

**Target**
5. **Early-warning alerts feed:** from `jobs/detect_alerts.py` (see 6.3). Each alert opens an **investigation card**: the metric, the spike chart, affected regions, the systems they share, and linked open complaints in the queue.
6. **System dependency graph:** nodes are regions and systems; edges show "region is served by system" and "complaints enter via system". Nodes are coloured by current alert status. Clicking a system shows its notes (age, vendor end-of-support, known issues) from `northwind_systems`.
7. **Category × month heatmap.**

**Stretch**
8. **Smart-meter projection:** the talking-point model from §9.2 as an interactive 2–5 year chart.
9. **Router impact tile:** live counters from the Replay (#1), shown on the dashboard.

### 6.3 Early-warning logic ("connect the dots")
- **Signals**, per region and month:
  - complaint count per category;
  - SLA breach rate;
  - billing exceptions per 1k accounts;
  - estimated read rate.
- **Detection:**
  - flag an alert when a signal's rolling z-score is ≥ 2, measured against the region's own trailing 6 months;
  - for slow drift, such as the breach rate, use a simple CUSUM change-point detector.
- **Connecting:** when the same signal fires in **two or more regions in the same month**, group those alerts. Attach the systems those regions share, found with the region → system graph. This produces an investigation such as: "Estimated-read complaints up in Barrowdale and Dunmoor; both served by SYS-01 and SYS-06; MeterHub estimation unchanged since 2012."
- **Honesty note:** real spikes in this dataset are modest (no category peaks above about 1.5x its average), so the live feed will be quiet. For the demo, add an **"inject scenario"** control (a stub) that plays a synthetic update, e.g. an outage in two regions, and shows the pipeline detect and connect it. We tell judges it's a simulated feed.
- Output goes to an `alerts` table: id, month, signal, regions, z, shared_systems, status. The router (#1) and the queue (#2) both read it.

### 6.4 Stubbing policy
If time runs short, stub **in this order** by replacing live computation with precomputed JSON (`data/aggregated_metrics.json` already contains most MVP tables): 9 → 8 → 7 → 6. Never stub panels 1–4, since they carry the story.

---

## 7. Component 2: Triage Queue

### 7.1 Purpose
The agent- and team-lead-facing app. It turns the 1,599-case backlog, plus anything new coming through the router, into an ordered to-do list. It uses #1's triage results for each case and #3's visual components and alerts.

### 7.2 Ranking
Calculate all timing live from dates, as of 2026-09-30. **Don't use the stored `sla_breach` flag for open tickets.**

- `age_days` = as_of − `date_opened`
- `overdue_days` = `age_days` − `sla_days` (negative means still inside SLA)
- `overdue_ratio` = `overdue_days` / `sla_days`, which puts a P1 two days over (5-day SLA) on the same scale as a P3 eight days over (20-day SLA)
- `priority_weight` = P1: 3, P2: 2, P3: 1

**Default ordering (composite):**
```
queue_score = priority_weight × max(overdue_ratio, 0)            # already breached
            + priority_weight × breach_risk × imminence          # not yet breached
            + 0.25 × transferred                                 # transferred cases breach 88% / reopen 29%
imminence   = 1 − days_until_breach / sla_days   (0 → 1 as the deadline nears)
```
- **Strict mode toggle:** sort by priority first, then overdue days descending. This matches "furthest past SLA and highest priority" literally, for anyone who distrusts a composite score.
- The weights sit in one config file and are shown in the UI ("Why is this case #1?").

### 7.3 Views and features
- **Queue table:** ID, priority, category, region, age, overdue (red past SLA, amber within 2 days), owner, transferred badge, alert badge, score. Filters by region, category, priority, owner and system; search by account.
- **Case detail drawer:**
  - the triage card from #1;
  - the account's complaint history timeline (reuse `analysis/complaint_histories.py` output);
  - any linked regional alert from #3.
- **Actions:** assign owner, change status (in progress / resolved / escalate), add a note. Actions are written to `case_events`. The source tables are never edited. Resolved cases leave the queue. This is enough to feel real in the demo.
- **Backlog planner:**
  - inputs: inflow per month (default: last-3-month average, about 1,200), closures per agent per month (derived from recent closures ÷ an assumed headcount — the headcount is an assumption we set and show), and extra agents (slider);
  - output: a projected backlog curve and **clearance date**, plus cost at **£46k per FTE per year**;
  - also shows the effect of the router: fewer transfers means faster closures, i.e. higher per-agent throughput.
- **(Stub, supports talking point #4) "Auto-resolved" lane:** a tab showing complaints the system would have answered automatically (high info-only likelihood + a matching answer template), with a "customer came back → moved to queue" example.

### 7.4 Deliverables and acceptance
- [ ] `engine/queue_score.py` with unit tests for ordering edge cases (P1 slightly overdue vs P3 very overdue; not-yet-breached vs breached)
- [ ] `GET /queue`, `GET /cases/{id}`, `POST /cases/{id}/events`
- [ ] Queue view + case drawer + planner
- [ ] New complaints from the Intake Simulator (#1) appear in the queue, ranked. **This is the demo moment that ties the three components together.**

---

## 8. Dropped: #5 Unified case-history integration layer

Replacing nightly batch files with an event bus across CaseTrack, CallCentre One, FieldForce and DocVault is a months-long integration programme. We can't credibly demo it, and it depends on vendor systems we don't have.

**How we address it in the pitch:** the router (#1) gets much of the benefit without that integration. If every complaint's case starts in the owning system with full context attached, there's much less to transfer. We can mention that the Helix CIS replacement (vendor support ends in 18 months) is the natural moment for Northwind to do the full integration later.

---

## 9. Talking points (explained, not built)

### 9.1 #4 Auto-resolution of information-only complaints
**Script:** "When a complaint arrives, the router checks whether it's likely to need only information, and whether we already have that information: an estimated-read explanation, a bill breakdown, or outage status from GridWatch. If so, the system sends the answer straight away and keeps the case on watch for 7 days. If the customer comes back, or there's no clear path to an answer, the case goes into the priority queue with everything attached."

**Evidence**
- 24% of complaints (about 3,000 a year) needed only information.
- Answering them with information works: they reopen no more often than other complaints.
- Each one costs £68 through the full complaint process today, so if half are auto-resolved that's roughly £100k a year, plus fewer calls at £7.40 each.
- Why this isn't another chatbot: the pilot failed because it tried to hold open-ended conversations. Its full-resolution rate fell from 16% to 10%, repeat contact rose from 31% to 45%, and customer satisfaction fell from 2.6 to 2.0. This approach answers only known question types, with data Northwind already holds, and passes everything else to a person.
- Where to start: "Other" (61% information-only) and "Service - poor communication" (53%).

### 9.2 #6 Smart-meter investment: where the next pound should go
**Script:** "The data doesn't say 'buy more smart meters everywhere'. It says **buy them in Barrowdale and Dunmoor**."

**Evidence**
- Barrowdale and Dunmoor have 0% smart meters, about 62% estimated reads, about 3x the billing exceptions per account and about 1.7x the billing complaints per account. They account for 46% of bill-correction value.
- **Key finding:** in the four smart regions, penetration rose from 30% to 81% over two years, but the estimated read rate stayed at about 22% (correlation ≈ 0). **In this data the benefit shows up by the first ~30% of coverage, and extra coverage adds nothing measurable.** We should present that as a hypothesis for Northwind to confirm.
- Recommendation: stop pushing coverage higher in regions already at 81%. **Redirect that budget to Barrowdale and Dunmoor**, targeting about 30% coverage and prioritising accounts with the most exceptions and estimated reads.

**Rough numbers for the 2–5 year projection**

| Item | Estimate |
|---|---|
| Meters for ~30% coverage in Barrowdale + Dunmoor | ~156k × £148 ≈ **£23M**, phased over 3–5 years |
| Full coverage (why it's been deferred twice) | 519k × £148 ≈ £77M |
| Billing/metering complaints avoided, if the two regions reach other-region rates | ~1,370/yr × £68 ≈ **£93k/yr** |
| Excess bill-correction value avoided | ~£160k/yr |
| Billing exceptions avoided | ~105k/yr. **Main value driver, but handling cost per exception is unknown**: at £34 (manual correction) it's up to ~£3.6M/yr; at a few pounds each it's much less |
| Field meter visits avoided | Share of 4,055 "meter visit required" outcomes × £92 |
| Regulator exposure | Fewer billing complaints feed directly into the £2.4M per quarter risk |

- Payback therefore ranges from **under 10 years to a few years**, depending mainly on exception handling cost. That's the one number we'd ask Northwind for. The projection chart (dashboard panel 8, stretch) should make the exception cost a slider.
- Secondary argument: Aurora Billing (COBOL, two developers left) serves only these two regions. Fewer estimated reads also means less reliance on a fragile rating engine.

---

## 10. Demo script (~5 minutes)

1. **The problem (45s).** Dashboard KPI header and SLA degradation chart: "Two years, from 44% to 92% breach."
2. **The cause (45s).** Transfer penalty panel: "Transferred complaints take 15 days longer and are 3x more likely to reopen, and whether a complaint gets transferred depends only on where it enters."
3. **The fix (60s).** Intake Simulator: submit a complaint and show the triage card, owner and legacy-vs-routed comparison. Then run the Replay: counters climb and the £ figure lands.
4. **The work (60s).** Switch to the Triage Queue: the complaint just submitted is ranked in place. Open the top case to show why it's #1, its history and its alert. Drag the planner slider to show the backlog clearance date moving.
5. **The early warning (45s).** Inject the scenario: the alert fires, groups two regions and names the shared systems.
6. **What's next (45s).** Talking points #4 (auto-resolution) and #6 (smart meters in Barrowdale and Dunmoor), each with one number.
7. **Close:** "No LLM, explainable, runs on data Northwind already has."

---

## 11. Build priorities

| Priority | Item | Owner |
|---|---|---|
| **P0** | `baselines` + `router.py` + `/triage` | TBD |
| **P0** | Dashboard panels 1–4 | TBD |
| **P0** | Queue table + ranking + case drawer | TBD |
| **P0** | Intake Simulator → new complaint appears in queue | TBD |
| **P1** | Replay with savings counters and sliders | TBD |
| **P1** | Alert detection + alerts feed + investigation card | TBD |
| **P1** | Backlog planner | TBD |
| **P2** | System dependency graph, heatmap | TBD |
| **P2** | Inject-scenario control, auto-resolved lane stub | TBD |
| **P2** | Smart-meter projection chart, router impact tile | TBD |
| **P2** | Gradient-boosted expected-days model | TBD |

Suggested split for three or four people: one on **engine + API**, one on **dashboard**, one on **queue**, and whoever is free takes **slides and the talking-point numbers**. Agree the API response shapes (§5.3 and the queue row) first, so the front end can build against mock JSON while the engine is still being written.

---

## 12. Risks and open questions

- **Synthetic data.** Some patterns look designed, e.g. SYS-04 never transfers and smart-meter penetration steps evenly. Present findings as "what this data shows" and name the assumptions.
- **No destination-system field.** We know a complaint was transferred but not where it went, so owner assignment is a policy we propose, not something learned from data.
- **The stored `sla_breach` flag doesn't match the dates for open tickets.** Calculate overdue from dates (see §3), and mention it: judges may appreciate that we checked.
- **Cost figures** come from Northwind's unit costs where possible. Everything else (build costs, exception handling cost) is an estimate and should be labelled as one on slides.
- **Currency:** the data doesn't name one; we use £.
- **Python dependencies:** pandas is installed. FastAPI and uvicorn will be needed, and scikit-learn only for the P2 model.
