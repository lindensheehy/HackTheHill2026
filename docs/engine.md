# Engine (Python backend logic)

All modules are importable from the repo root (`python -m ...`). Frames come from `engine/db.py`:
- `complaints()` adds `is_open`, `month` (opening YYYY-MM) and parsed dates; cached via `lru_cache` on the raw table.
- Also available: `closed_complaints()`, `meter_reads()` (+`exceptions_per_1k` = exceptions/accounts×1000), `systems()`, `unit_costs()`, `monthly_kpis()`, `ai_pilot()`.
- Helpers: `region_systems()` → {region: [sys ids]} (latest month), `system_names()`, `label(id)`.
- Storage and misc: `store()` → the app store (engine/store.py; see integrations.md), `SOURCE_TABLES`, `dumps()` (numpy-safe JSON), `AS_OF`/`AS_OF_TS`.
- Never open SQLite directly for app tables; always go through `db.store()` so Postgres works too.

## cost_model.py
- `costs()`: dict keyed call, complaint, complaint_transferred, bill_correction, field_visit, smart_meter, agent_fte, ai_pilot, regulator_penalty_quarter, compensation. `cost(key)` returns one.
- `transfer_penalty()`: {transfer_share, days/breach/reopen/cost:{transferred,not}, per_avoided:{gbp,days,reopens,breaches}}, from all closed cases.
- `expected_cost(risk) = risk·121 + (1−risk)·68`.

## build_baselines.py (`python -m engine.build_baselines`)
Writes kind/key/value rows to `baselines`. Recency weighting: closed cases opened in the last 12 months get weight 2.

| kind | key | value | source |
|---|---|---|---|
| resolution_path | `cat\|pri`, `cat\|*` | list sorted by share: {action, share(weighted), median_days, reopen_rate, n} | closed, **non-transferred** |
| info_only | `cat\|channel`, `cat\|*` | {rate, n, category_rate}; rate = (Σinfo + 50·cat_rate)/(n+50) | closed |
| outcomes | `cat\|pri\|t`, `cat\|*\|t` (t=0/1) | {mean_days, median_days, breach, reopen, n} (weighted) | closed |
| transfer_rate | entry sys id | {rate, n, by_category} | all complaints |
| breach_survival | `pri\|t` | {sla_days, p_breach_given_age[0..sla], n} | Kaplan-Meier on last 12 months of intake; open cases censored at current age. value[a] = S(sla)/S(a); last element = 1.0 |
| region_signals | region | {month, accounts, estimated_read_rate, smart_meter_penetration, exceptions_per_1k, systems[]} | latest meter month |
| global | transfer_penalty, as_of | | |

`load()` returns {kind:{key:value}} and caches in-process (`_cache`). It builds if the table is empty. `build()` clears the cache.
Current P(breach | open at day 0) ≈ 0.78–0.86 non-transferred and ≈ 0.95–0.97 transferred: nearly everything breaches now.

## router.py: `route(intake, tables, context=None) -> TriageResult` (pure, no I/O)
intake: channel, category, priority, region, optional account_id, entry_system, complaint_id. Unknown extra keys are ignored.
1. **Entry** = intake.entry_system or CHANNEL_ENTRY[channel] (Phone/Email/Post/Regulator referral→SYS-05; Web form/Social→SYS-03).
2. **Owner** is a policy: always `SYS-04 CaseTrack`; team from TEAMS:
   - Billing (disputed, estimated read) → Billing Resolution
   - Metering - no read taken → Metering Operations
   - Payment → Payments & Arrears
   - Missed appointment → Field Scheduling
   - Poor communication and Other → Customer Relations
   - Supply → Network Operations
   - Water → Water Operations

   linked_systems:
   - Billing/metering teams with a billing category → the region's systems (else SYS-02).
   - Otherwise TEAM_SYSTEMS: Payments→02; Field→08; Customer Relations→14; Network→09,08; Water→10,08.
3. **transfer_risk** = 0 if entry is SYS-04, else transfer_rate[entry].rate (~0.46).
4. **resolution_path**: top 3 of `cat|pri` (fallback `cat|*`). **info_only_likelihood** from `cat|channel` (fallback `cat|*`).
5. **Routed vs legacy**:
   - routed = outcomes[cat|pri|0].
   - legacy = risk·outcomes[…|1] + (1−risk)·outcomes[…|0], applied to mean_days, breach and reopen.
   - cost: routed £68; legacy expected_cost(risk). Invariant: routed ≤ legacy.
6. **context** (from caller): region_alert {alert_id, summary}, account_prior_complaints.
7. **reasons[]**, in order:
   - owner sentence
   - transfer-rate sentence (or "Entered via CaseTrack…")
   - top resolution
   - info-only sentence if ≥ 0.4
   - historical-comparison sentence if risk > 0 ("…closed ~N days sooner… an expectation, not a guarantee"; never "saves")
   - "Active alert: …"
   - prior complaints
   - "no smart meters" for 0%-penetration regions with a billing category

Output keys:
- complaint_id; intake{channel, category, priority, region, account_id, sla_days}
- owner{system, team, linked_systems[]}; legacy_route{entry_system, transfer_risk}
- resolution_path[{action, share, median_days, reopen_rate}]; info_only_likelihood
- expected_days, breach_risk, reopen_risk, cost: each {routed, legacy}
- context{region_alert, region_alert_id, region_systems[], region_signals{estimated_read_rate, smart_meter_penetration, exceptions_per_1k}, account_prior_complaints}
- queue_score (0); reasons[]

System labels are "SYS-xx Name". `route_live(intake)` = route with `build_baselines.load()` + `context.gather(intake)`.

## context.py
- `all_complaints()` = source complaints + intake_complaints. Intake rows get: status Open, transferred 0, reopened 0, `from_intake=True`, and the `triage` JSON column. Source rows get `from_intake=False`, `triage=None`.
- `account_history(acc, exclude_id)`: sorted by date.
- `alert_for(region, category)`: the strongest **active** alert whose regions include the region and whose `detail.related_categories` include the category. Returns {alert_id, summary+" (z = x)", synthetic}.
- `gather(intake)` → {account_prior_complaints, region_alert}.

## queue_score.py + queue_config.json
Config: priority_weight {P1:3, P2:2, P3:1}, transferred_bonus 0.25, alert_bonus 0.25, amber_days 2, imminence_horizon_days 20, assumed_complaint_fte 60.
```
age_days = as_of − date_opened;  overdue_days = age − sla;  overdue_ratio = overdue/sla;  breached = overdue > 0
imminence   = clip(1 − days_left/20, 0, 1)          (days_left = −overdue_days)
breach_risk = 1 if breached else survival[pri|transferred][clip(age)]
score = breached ? w·(1 + overdue_ratio) : w·breach_risk·imminence
      + 0.25·transferred + 0.25·alert                (rounded to 3 dp)
overdue_state = red if breached; amber if days_left ≤ 2; else green
```
- `score_frame(df, survival, cfg, as_of, alert_flags)` adds all columns above plus `why[]` (the arithmetic spelled out).
- `rank(df, strict)`: by score desc. Strict mode sorts by priority, then overdue_days desc.
- Examples: a fresh P1 ≈ 3·0.78·0.75 ≈ 1.76; a P3 one day over ≈ 1.05; the demo Barrowdale P2 intake ≈ 1.09 → rank ~955 of 1,540.

## queue.py (service layer)
- Constants: AUTO_TEMPLATES for 5 categories (Other, poor communication, water, supply, estimated read); AUTO_THRESHOLD 0.45; AUTO_MAX_AGE 14; AUTO_WATCH_DAYS 7. EVENT_TYPES {assign, status, note, auto_bounce}; STATUSES {in_progress, resolved, escalated}.
- `open_cases(include_auto)` takes open rows from all_complaints, then:
  - applies the latest `status`/`assign` event per case; `resolved` rows are dropped; `owner_team` defaults to TEAMS[category]; adds the notes count;
  - sets alert flags (alert_id, alert_summary) and scores the rows;
  - sets `in_auto_lane` = likelihood ≥ 0.45 AND template exists AND age ≤ 14 AND not bounced AND workflow_status == new. Lane rows are excluded unless include_auto.
  - Counts at as-of: 1,539 in the queue + 60 in the lane = 1,599.
- `queue(strict, filters, limit, offset)`:
  - Filters: region/category/priority are exact; owner→owner_team; system→source_system; search = substring of account_id (upper-cased) or complaint_id.
  - Returns {rows[] (ROW_FIELDS + rank), summary{total, by_priority, breached, amber, median_overdue_days, max_overdue_days, stored_flag_breached_share, from_intake}, config, strict}.
- `auto_lane()` → {rows[] (+auto_template, watch_until = opened+7), bounced[], threshold, templates, watch_days}.
- `case_detail(id)`:
  - Returns {case, triage, history[], events[], alert|null}.
  - case = row + rank (position among non-lane cases) + in_auto_lane + auto_template; a closed case returns {complaint_id, status, closed:true}.
  - triage is re-routed live with entry = source_system. For intake rows it uses the **original** entry system parsed from the stored triage; without that, the stored SYS-04 would show no legacy difference.
- `case_summary(case, triage, history, alert)` → {what_happened, next_action, owner, blockers[], due_date}, from deterministic rules. Blockers: escalated, past SLA, transferred (CaseTrack loses history), field action (FieldForce not linked), regional alert, repeat complainant; otherwise "Nothing blocking". `case_detail` includes it as `summary`.
- `add_event` validates type and status. `customer_help` also inserts a `status=escalated` event in the same transaction.
- `create_intake(intake)`:
  - id = NW-(max(source, intake)+1); date_opened = as-of; source_system SYS-04; account defaults to a synthetic ACC-9xxxxx; triage JSON stored.
  - Returns TriageResult + queue_rank, queue_size, in_auto_lane (rank is null when the case lands in the lane).
- `reset_demo()` deletes intake_complaints and case_events, then `detect_alerts.reset_scenario()` (synthetic alerts and signal points).

ROW_FIELDS:
- identity/attributes: complaint_id, priority, category, region, channel, source_system, account_id, date_opened, sla_days
- timing/score: age_days, overdue_days, overdue_ratio, overdue_state, breach_risk, queue_score, why
- flags/workflow: transferred_between_systems, owner_team, workflow_status, alert_id, alert_summary, from_intake, notes, bounced_from_auto, info_only_likelihood

## jobs/detect_alerts.py (`python -m jobs.detect_alerts`)
- `build_panel()` gives long rows (region, month, signal, category, value). Signals:
  - `complaints:<category>`: monthly opened count;
  - `sla_breach_rate`: per opening month, breach = closed flag, or open and age > sla; only months ≤ 2026-08;
  - `exceptions_per_1k`, `estimated_read_rate`: from meter reads.
- `detect(panel, months)`:
  - **Spikes:** z vs the region's own trailing 6 points. sd floor = √mean for counts, else 5%·mean. Fire at **z ≥ 3**; counts also need ≥ 10 and ≥ 1.3× the trailing mean.
  - **sla_breach_rate** uses CUSUM instead: baseline = first 6 months, sd floor 0.02, k = 0.5, h = 5. It fires once per region (first crossing) and reports z = the CUSUM value.
- `group(found, synthetic)`:
  - Groups by (month, signal); regions sorted; shared_systems = intersection of the regions' systems.
  - summary: "<label> up|drifting up in A and B; all served by X and Y".
  - status is active if synthetic or month ≥ 2026-08, else historical.
  - alert_id is `AL-`/`SIM-` + month + sha1(signal|regions)[:6]: deterministic across runs.
  - detail = {summary, label, method (zscore|cusum), related_categories (the category itself, or SIGNAL_CATEGORY for meter signals), per_region[{region, value, baseline, z}], system_notes[{system, note}]}.
- **Storage:** detection reads the stored `signal_points` feed, not the in-memory panel. See integrations.md for materialize/load_panel/ingest.
- `run()` = materialize + run_detection. It replaces real alerts (synthetic ones are kept). Current result: 23 historical, 0 active.
- **Scenario:**
  - SCENARIO month 2026-10 for Barrowdale + Dunmoor: estimated-read complaints ×2.6, disputed ×1.5, exceptions ×1.45, estimated read +0.12.
  - `inject_scenario()` clones the 2026-09 feed rows as 2026-10, applies the multipliers, **writes them to signal_points as synthetic**, detects on the stored feed restricted to 2026-10, and saves.
  - Result: 4 grouped alerts (est-read complaints z≈13.5, exceptions ≈10.3, disputed ≈5.3, estimated read rate ≈5), all naming SYS-01 + SYS-06.
- `reset_scenario()` removes synthetic alerts and synthetic points. `load_alerts(status)` returns them with JSON fields decoded, ordered by month desc, then z desc.

## dashboard.py (all return JSON-able dicts)
- `monthly()`: per KPI month, returns
  - volumes and KPIs: opened, closed, avg_days_to_close, fcr, regulator_score, inbound_calls, cost_to_serve;
  - breach_rate (opening cohort, closed only) and breach_rate_3m (rolling);
  - transfer_rate; open_share; incomplete (open_share > 5%).
- `kpi_header()`:
  - tiles (opened, avg_days_to_close, breach_rate, fcr, regulator_score), each {value, prior (12 months earlier), series, better: up|down, format}. breach_rate uses the latest complete cohort (Jun-26 vs Jun-25).
  - Also penalty_per_quarter, and first-month values.
- `transfer_panel()` → penalty, slowest_1pct, by_entry_system, spread_outside_casetrack{dim:{min, max, values}}, last_12m{transfers, gbp, days, reopens, breaches}.
- `regions()` → regions[]{…} and estimated_read_trend. Per region:
  - accounts; focus flag;
  - last-12-month metrics: complaints_12m, complaints_per_1k, billing_complaints_per_1k, breach_rate, transfer_rate;
  - meter data: estimated_read_rate, smart_meter_penetration(+_start), exceptions_per_1k (12-month average);
  - bill_correction_value(+_share), open_now, systems[].
- `heatmap()` → months, rows[{category, counts[], index[] (count ÷ the category's mean)}].
- `graph(active_alerts)` →
  - nodes: systems used + regions, with alert flags; systems carry `info` from northwind_systems.
  - edges: served_by (region→system) and transfers_to (entry→SYS-04, labelled with the rate).
- `smart_meter()` → inputs for the client projection plus scatter points. `talking_points()` → info_only stats, ai_pilot rows, ai_pilot_cost.

## replay.py
`replay()` covers complaints opened ≥ 2026-04 (7,110).
- Per month: complaints, outside_casetrack, actual_transfers, expected_transfers (Σ entry rates), weeks[{week, complaints, transfers}], ticker (24 sampled rows with seed 7, routed: id, date, category, priority, region, entry, team, transferred, days_saved).
- Also returns per_avoided, defaults {adoption .8, avoidance .6}, annual_transfers (4,795), total_complaints.
- Savings are computed client-side: avoided = transfers × adoption × avoidance.

## planner.py
`defaults()` → {as_of, backlog (open incl. lane, 1,599), inflow (mean of the last 3 KPI months opened ≈ 1,236), closures (≈ 1,152), assumed_fte 60, per_agent, fte_cost, transfer_share (recent closures ≈ 0.341), cost{not, transferred}, router_defaults}. The projection is client-side (see web.md).
