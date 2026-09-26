# Data

## Source: `Northwind_Challenge_Data/data.db` (SQLite, read-only; CSVs alongside are the same data)
| Table | Rows | Columns (notes) |
|---|---|---|
| northwind_complaints | 25,416 | complaint_id `NW-100001..NW-125416`; date_opened/date_closed (text `YYYY-MM-DD`, closed null if open); status ∈ {Closed, Closed - reopened, Open}; channel; category; priority P1/P2/P3; region; source_system (entry system); transferred_between_systems 0/1; sla_days; days_to_close (null if open); sla_breach; reopened; resolution_action (null if open); resolvable_by_information_only; bill_correction_value; account_id `ACC-######` |
| northwind_meter_reads | 144 | month `YYYY-MM` × 6 regions; accounts; estimated_read_rate; smart_meter_penetration; billing_exceptions_raised; systems_serving_region (`SYS-xx/SYS-yy`) |
| northwind_monthly_kpis | 24 | month 2024-10..2026-09; complaints_opened/closed; avg_days_to_close; first_contact_resolution_rate; inbound_calls; cost_to_serve_per_account; regulator_satisfaction_score_of_5 |
| northwind_systems | 15 | system_id SYS-01..15, system_name, purpose, year_installed, vendor, tech_stack, records_held, integration_method, annual_run_cost, owning_function, notes |
| northwind_unit_costs | 10 | item, unit_cost, unit, source_note |
| northwind_ai_pilot_2025 | 9 | month 2025-01..09; assistant_sessions; fully_contained_rate; escalated_to_agent_rate; abandoned_rate; repeat_contact_within_7_days_rate; assistant_csat_of_5; complaint_raised_after_session_rate |

Domains:
- channel: Phone, Web form, Email, Post, Social, Regulator referral
- category (9): Billing - disputed amount, Billing - estimated read, Metering - no read taken, Payment - plan or arrears, Service - missed appointment, Service - poor communication, Supply - interruption, Water - pressure or quality, Other
- region (6): Ashford, Barrowdale, Calderfield, Dunmoor, Eastmarch, Fenwick. **Barrowdale + Dunmoor** = SYS-01 Aurora Billing + SYS-06 MeterHub, 0% smart meters. The other four = SYS-02 Helix CIS + SYS-07 SmartRead.
- source_system ∈ {SYS-01, SYS-03, SYS-04, SYS-05}. **SYS-04 CaseTrack never transfers**; the others transfer ~46%.
- SLA: P1=5, P2=10, P3=20 days (1,533 / 6,017 / 17,866 rows).
- Verified identities: `sla_breach == (days_to_close > sla_days)` and `days_to_close == date_closed − date_opened` hold for 100% of closed rows.
- Resolution actions (10): Bill corrected and re-issued, Refund or credit applied, Information provided only, No action - explained to customer, Meter visit required, Payment plan amended, Appointment rebooked by agent, Compensation payment issued, Apology and manual process fix, Field repair required.
- Accounts: 24,737 have 1 complaint, 332 have 2, and 5 have 3. Demo accounts with history: ACC-980200 (Barrowdale), ACC-730009 (Fenwick), ACC-615081, ACC-489331.

Unit costs (£): call 7.4; complaint 68; transferred complaint 121; manual bill correction 34; field visit 92; smart meter 148; agent FTE 46,000/yr; AI pilot 640,000/yr; regulator penalty 2,400,000/quarter; compensation 40.

Systems referenced by the app: 01 Aurora Billing (COBOL, 2 devs left), 02 Helix CIS (support ends in 18 months), 03 Northwind Connect, 04 CaseTrack, 05 CallCentre One, 06 MeterHub (estimation unchanged since 2012), 07 SmartRead Gateway, 08 FieldForce, 09 GridWatch, 10 AquaTrack, 14 DocVault, 15 AskNorthwind AI pilot (paused).

## App store: `data/app.db` or Postgres (schema in `engine/store.py:_COMMON`; see integrations.md)
| Table | Columns | Written by |
|---|---|---|
| baselines | kind, key, value(JSON); PK(kind,key) | build_baselines.build() |
| alerts | alert_id PK, month, signal, category, regions(JSON list), z, shared_systems(JSON), status(active/historical), synthetic(0/1), detail(JSON) | detect_alerts.save() |
| case_events | event_id autoinc, complaint_id, ts(ISO local), type(assign/status/note/auto_bounce/customer_help), value, note | queue.add_event() |
| intake_complaints | complaint_id PK, date_opened(=as-of), channel, category, priority, region, source_system(always SYS-04), account_id, sla_days, triage(JSON TriageResult), created_ts | queue.create_intake() |
| signal_points | time, month, region, signal, category, value, synthetic, source(derived/ingest/simulated); hypertable on Timescale | detect_alerts.materialize/ingest/inject_scenario |
| ai_briefs | alert_id, evidence_hash, mode, content(JSON), created_ts; PK(alert_id, evidence_hash) | assistant.brief() (Gemini output only) |
| usage | day(UTC), service(gemini/elevenlabs), units, calls; PK(day, service) | usage.add() |
| (Postgres only) the 6 source tables | copied verbatim | jobs/import_source.py |

## Evidence numbers (reproduced by the code; use them in copy and slides)
- Closed-case transfer share 34%. Transferred vs not: 38.2 vs 23.0 days, 87.7% vs 69.0% breach, 29.2% vs 8.9% reopen, £121 vs £68.
- Per avoided transfer: £53, 15.2 days, 0.203 reopens, 0.187 breaches.
- Slowest 1% (>85 days, n=239): 100% transferred. Outside CaseTrack, transfer rate spans 44–49% across every category/channel/priority/region.
- Last 12 months: 4,795 transfers → £254k, 73,260 complaint-days, 975 reopens, 898 breaches (upper bound). At the default 80%×60%: ~2,302 avoided → £122k, 35k days, 468 reopens, 431 breaches.
- Breach rate by opening-month cohort (closed only): 44% (Oct-24) → ~93% (Jun-26, latest cohort with <5% still open). Jul-26 onward cohorts are incomplete.
- KPIs Sep-26 vs Sep-25: opened 1,251 vs 1,020; avg days 38.2 vs 28.6; FCR 41% vs 52%; regulator 2.58 vs 3.47 (4.3 at start).
- Open backlog 1,599 (35 P1 / 219 P2 / 1,345 P3). Stored flag says 98% breached; by dates 835 of the 1,539 queued are past SLA, median overdue ≈ 1–2 days, max 106.
- Last-3-month inflow ≈ 1,236/month vs closures ≈ 1,152/month: the backlog is growing.
- Info-only: 24.6% of closed (~2,932/yr). Other 61%, poor communication 53%, water 33%, … no read taken 11%. Reopen 16.2% vs 15.7%. Half auto-answered ≈ £100k/yr.
- AI pilot: fully contained 16% → 10%, repeat contact 31% → 45%, CSAT 2.6 → 2.0.
- Smart meters: focus regions 519k accounts, ~62% estimated reads vs ~22%, exceptions 25.1 vs 8.7 per 1k per month. Correlation of penetration vs estimated-read rate in the smart regions ≈ −0.01 (the "benefit arrives by ~30%" hypothesis). 30% coverage = 155,700 meters ≈ £23M; avoids ~102k exceptions/yr, ~1,375 billing complaints/yr (£93k), and ~£161k/yr excess bill correction; 4,055 "meter visit required" outcomes in 2 years.

## Data caveats
- Synthetic: patterns look designed (CaseTrack never transfers; penetration steps evenly). Present findings as "what this data shows".
- No destination-system field: the owner policy is proposed, not learned.
- Recent closed cohorts are right-censored (fast closes over-represented). This is why Kaplan-Meier is used and incomplete months are shaded.
- Real month-over-month spikes are modest (no category above ~1.5× its average), so the live alert feed is quiet at the as-of date.
