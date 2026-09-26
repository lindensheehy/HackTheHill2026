# Database Schema

Source database: `data.db`

## northwind_ai_pilot_2025

Rows: 9

| Column | Type |
| --- | --- |
| month | TEXT |
| assistant_sessions | INTEGER |
| fully_contained_rate | REAL |
| escalated_to_agent_rate | REAL |
| abandoned_rate | REAL |
| repeat_contact_within_7_days_rate | REAL |
| assistant_csat_of_5 | REAL |
| complaint_raised_after_session_rate | REAL |

## northwind_complaints

Rows: 25416

| Column | Type |
| --- | --- |
| complaint_id | TEXT |
| date_opened | DATETIME |
| date_closed | DATETIME |
| status | TEXT |
| channel | TEXT |
| category | TEXT |
| priority | TEXT |
| region | TEXT |
| source_system | TEXT |
| transferred_between_systems | INTEGER |
| sla_days | INTEGER |
| days_to_close | INTEGER |
| sla_breach | INTEGER |
| reopened | INTEGER |
| resolution_action | TEXT |
| resolvable_by_information_only | INTEGER |
| bill_correction_value | REAL |
| account_id | TEXT |

## northwind_meter_reads

Rows: 144

| Column | Type |
| --- | --- |
| month | TEXT |
| region | TEXT |
| accounts | INTEGER |
| estimated_read_rate | REAL |
| smart_meter_penetration | REAL |
| billing_exceptions_raised | INTEGER |
| systems_serving_region | TEXT |

## northwind_monthly_kpis

Rows: 24

| Column | Type |
| --- | --- |
| month | TEXT |
| complaints_opened | INTEGER |
| complaints_closed | INTEGER |
| avg_days_to_close | REAL |
| first_contact_resolution_rate | REAL |
| inbound_calls | INTEGER |
| cost_to_serve_per_account | REAL |
| regulator_satisfaction_score_of_5 | REAL |

## northwind_systems

Rows: 15

| Column | Type |
| --- | --- |
| system_id | TEXT |
| system_name | TEXT |
| purpose | TEXT |
| year_installed | INTEGER |
| vendor | TEXT |
| tech_stack | TEXT |
| records_held | INTEGER |
| integration_method | TEXT |
| annual_run_cost | INTEGER |
| owning_function | TEXT |
| notes | TEXT |

## northwind_unit_costs

Rows: 10

| Column | Type |
| --- | --- |
| item | TEXT |
| unit_cost | REAL |
| unit | TEXT |
| source_note | TEXT |
