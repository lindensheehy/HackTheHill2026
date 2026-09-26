# Northwind Complaints: Nuanced Analysis

Generated from `data/data.db` (table `northwind_complaints`) by `analysis/analysis_nuanced.py`.

## Key Takeaways

- **Worst SLA cell:** Billing - estimated read at P1 breaches 83.6% of the time.
- **Transfer penalty:** transferred tickets take 38.2 days on average vs 23.0 (1.67x), with a breach rate of 87.7% vs 69.0%.
- **SLA reality gap:** the 10-day SLA cohort averages 17.2 days (1.72x target).
- **Regional bottleneck:** Dunmoor has the highest breach rate (76.1%, mean 28.3 days).
- **Financial liability:** 1,345,189.54 in bill corrections; Billing - disputed amount accounts for 72.2% (970,557.26).
- **Repeat accounts:** 291 of 23,523 accounts have more than one closed complaint; 25 have more than one financial complaint.
- **Information-only risk:** complaints resolvable by information alone reopen at 16.2% vs 15.7% for the rest.
- **Least durable fix:** "Refund or credit applied" reopens 17.5% of the time.
- **Channel:** Social has the highest information-only resolvable rate (25.6%).
- **SLA trend:** the 3-month rolling breach rate moved from 48.3% (2024-12) to 91.4% (2026-09), peaking at 92.8% in 2026-07.
- **Sharpest spike:** Other peaked at 43 in 2026-06 (1.54x its monthly mean); busiest calendar months: May, Sep, Jun.
- **Highest-friction system:** SYS-01 (46.2% transferred, mean 30.2 days to close).

## Data Preparation & Long-Tail

### Dataset Overview

| metric | value |
| --- | --- |
| Total complaints | 25,416 |
| Open (excluded from resolution/SLA/financial metrics) | 1,599 |
| Closed (incl. reopened) | 23,817 |
| Date range (opened) | 2024-10-01 to 2026-09-30 |
| Distinct accounts | 25,074 |
| Long-tail threshold (p99 days_to_close) | 84.84 |
| Long-tail complaints | 239 |

### Long-Tail Profile

_Share of long-tail complaints in each segment vs. all closed complaints, sorted by over-representation (percentage points)._

| index | long_tail_% | all_closed_% | over_representation_pp |
| --- | --- | --- | --- |
| priority: P3 | 100.00 | 69.37 | 30.63 |
| category: Billing - disputed amount | 53.97 | 31.42 | 22.55 |
| category: Billing - estimated read | 36.40 | 18.83 | 17.57 |
| source_system: SYS-05 | 41.00 | 24.94 | 16.06 |
| source_system: SYS-01 | 33.05 | 25.46 | 7.59 |
| source_system: SYS-03 | 25.94 | 24.65 | 1.30 |
| category: Other | 0.42 | 2.64 | -2.22 |
| category: Water - pressure or quality | 0.84 | 5.26 | -4.42 |
| category: Supply - interruption | 3.35 | 8.68 | -5.33 |
| category: Payment - plan or arrears | 0.84 | 6.39 | -5.55 |
| category: Service - missed appointment | 1.26 | 6.84 | -5.59 |
| priority: P1 | 0.00 | 6.29 | -6.29 |

### Long-Tail vs. All Closed

| subset | transferred_% | reopened_% | mean_days_to_close |
| --- | --- | --- | --- |
| Long-tail | 100.00 | 28.87 | 93.67 |
| All closed | 34.22 | 15.85 | 28.19 |

## A. SLA Performance & Bottlenecks

### Breach Rate (%) by Category & Priority

_Closed complaints only._

| category | P1 | P2 | P3 | All |
| --- | --- | --- | --- | --- |
| Billing - estimated read | 83.62 | 79.44 | 82.12 | 81.56 |
| Billing - disputed amount | 73.55 | 78.24 | 80.46 | 79.49 |
| All | 71.50 | 75.11 | 75.81 | 75.37 |
| Service - poor communication | 64.81 | 69.75 | 72.86 | 71.61 |
| Water - pressure or quality | 68.24 | 75.18 | 70.20 | 71.19 |
| Payment - plan or arrears | 56.98 | 71.26 | 71.57 | 70.68 |
| Other | 64.29 | 76.26 | 68.90 | 70.22 |
| Supply - interruption | 70.99 | 71.89 | 69.21 | 70.00 |
| Service - missed appointment | 69.23 | 69.62 | 70.10 | 69.94 |
| Metering - no read taken | 63.55 | 70.95 | 70.09 | 69.85 |

### System Transfer Penalty

| transferred_between_systems | complaints | mean_days | median_days | breach_rate_pct | reopen_rate_pct |
| --- | --- | --- | --- | --- | --- |
| Not transferred | 15,668 | 22.97 | 21.00 | 68.96 | 8.90 |
| Transferred | 8,149 | 38.24 | 36.00 | 87.69 | 29.23 |

### SLA Target vs. Reality

| sla_days | complaints | mean_days | median_days | p90_days | breach_rate_pct | mean_overrun_days | mean_vs_target_ratio |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | 1,498 | 8.46 | 8.00 | 15.00 | 71.50 | 3.46 | 1.69 |
| 10 | 5,798 | 17.19 | 16.00 | 30.00 | 75.11 | 7.19 | 1.72 |
| 20 | 16,521 | 33.85 | 32.00 | 59.00 | 75.81 | 13.85 | 1.69 |

### Regional Bottlenecks

_Rank 1 = worst._

| region | complaints | breach_rate_pct | mean_days | median_days | breach_rank | days_rank |
| --- | --- | --- | --- | --- | --- | --- |
| Dunmoor | 4,061 | 76.14 | 28.25 | 25.00 | 1 | 2 |
| Barrowdale | 4,020 | 75.90 | 28.71 | 25.00 | 2 | 1 |
| Calderfield | 3,848 | 75.60 | 27.79 | 25.00 | 3 | 6 |
| Eastmarch | 3,912 | 75.15 | 28.21 | 25.00 | 4 | 3 |
| Ashford | 4,026 | 74.79 | 28.18 | 26.00 | 5 | 4 |
| Fenwick | 3,950 | 74.63 | 28.01 | 25.00 | 6 | 5 |

## B. Financial Impact (Bill Corrections)

### Total Financial Liability

_Closed complaints; missing corrections treated as 0._

| metric | value |
| --- | --- |
| Total bill correction value | 1,345,189.54 |
| Complaints with a correction | 7,874 |
| Share of closed complaints with a correction (%) | 33.06 |
| Mean correction (where > 0) | 170.84 |
| Median correction (where > 0) | 160.72 |
| Largest single correction | 687.76 |

### Correction by Category

| category | complaints | corrections | total_value | median_value_where_corrected | share_of_total_pct |
| --- | --- | --- | --- | --- | --- |
| Billing - disputed amount | 7,484 | 5,758 | 970,557.26 | 158.25 | 72.15 |
| Billing - estimated read | 4,485 | 1,862 | 329,885.92 | 167.50 | 24.52 |
| Metering - no read taken | 2,949 | 254 | 44,746.36 | 166.84 | 3.33 |
| Other | 628 | 0 | 0.00 |  | 0.00 |
| Payment - plan or arrears | 1,521 | 0 | 0.00 |  | 0.00 |
| Service - missed appointment | 1,630 | 0 | 0.00 |  | 0.00 |
| Service - poor communication | 1,800 | 0 | 0.00 |  | 0.00 |
| Supply - interruption | 2,067 | 0 | 0.00 |  | 0.00 |
| Water - pressure or quality | 1,253 | 0 | 0.00 |  | 0.00 |

### Account Repeat Summary

| metric | accounts |
| --- | --- |
| Accounts with a closed complaint | 23,523 |
| Accounts with 2+ complaints | 291 |
| Accounts with 2+ financial complaints | 25 |

### Top 10 Accounts by Correction Value

| account_id | complaints | financial_complaints | total_value |
| --- | --- | --- | --- |
| ACC-698468 | 1 | 1 | 687.76 |
| ACC-217364 | 1 | 1 | 611.98 |
| ACC-237534 | 1 | 1 | 602.61 |
| ACC-164312 | 1 | 1 | 597.30 |
| ACC-277584 | 1 | 1 | 594.31 |
| ACC-765405 | 1 | 1 | 593.41 |
| ACC-567718 | 1 | 1 | 586.89 |
| ACC-915562 | 1 | 1 | 584.65 |
| ACC-320792 | 2 | 2 | 583.18 |
| ACC-611735 | 1 | 1 | 579.84 |

### Top 10 Accounts by Financial Complaint Volume

_A financial complaint is one with a non-zero bill correction._

| account_id | complaints | financial_complaints | total_value |
| --- | --- | --- | --- |
| ACC-320792 | 2 | 2 | 583.18 |
| ACC-807845 | 2 | 2 | 459.22 |
| ACC-214026 | 2 | 2 | 455.42 |
| ACC-828615 | 2 | 2 | 448.67 |
| ACC-634600 | 2 | 2 | 447.59 |
| ACC-202749 | 2 | 2 | 379.48 |
| ACC-472454 | 2 | 2 | 378.24 |
| ACC-301174 | 2 | 2 | 339.36 |
| ACC-730009 | 2 | 2 | 337.63 |
| ACC-583852 | 3 | 2 | 330.18 |

## C. Reopen Rate & Resolution Efficacy

### The "Information Only" Risk

_Reopen rate split by whether the complaint was resolvable by information alone._

| resolvable_by_information_only | complaints | reopened | reopen_rate_pct |
| --- | --- | --- | --- |
| No | 17,952 | 2,826 | 15.74 |
| Yes | 5,865 | 950 | 16.20 |

### Reopen Rate by Resolution Action

| resolution_action | complaints | reopened | reopen_rate_pct | info_only_resolvable_pct |
| --- | --- | --- | --- | --- |
| Refund or credit applied | 1,785 | 312 | 17.48 | 0.00 |
| Information provided only | 4,783 | 777 | 16.25 | 100.00 |
| Compensation payment issued | 764 | 124 | 16.23 | 0.00 |
| Field repair required | 2,074 | 334 | 16.10 | 0.00 |
| No action - explained to customer | 1,082 | 173 | 15.99 | 100.00 |
| Meter visit required | 4,055 | 643 | 15.86 | 0.00 |
| Bill corrected and re-issued | 6,089 | 953 | 15.65 | 0.00 |
| Apology and manual process fix | 976 | 147 | 15.06 | 0.00 |
| Payment plan amended | 1,122 | 160 | 14.26 | 0.00 |
| Appointment rebooked by agent | 1,087 | 153 | 14.08 | 0.00 |

### Channel-Specific Resolution

| channel | complaints | info_only_resolvable_pct | reopen_rate_pct | breach_rate_pct |
| --- | --- | --- | --- | --- |
| Social | 1,393 | 25.63 | 15.58 | 75.81 |
| Regulator referral | 1,144 | 25.35 | 15.47 | 75.87 |
| Phone | 12,967 | 24.82 | 15.89 | 75.34 |
| Email | 2,774 | 24.62 | 16.15 | 74.87 |
| Post | 1,190 | 24.12 | 14.29 | 73.28 |
| Web form | 4,349 | 23.66 | 16.16 | 76.09 |

## D. Time-Series & Trends

### Volume & SLA Degradation by Month

_`breach_rate_pct` and the 3-month rolling rate use closed complaints only. Recent months have more tickets still open, so their closed-only rates skew toward fast resolutions._

| month_year | opened | still_open | closed | mean_days | breach_rate_pct | rolling_3m_breach_pct |
| --- | --- | --- | --- | --- | --- | --- |
| 2024-10 | 912 | 0 | 912 | 17.61 | 43.97 |  |
| 2024-11 | 830 | 0 | 830 | 19.44 | 49.88 |  |
| 2024-12 | 951 | 0 | 951 | 19.46 | 51.10 | 48.31 |
| 2025-01 | 985 | 0 | 985 | 20.50 | 55.03 | 52.13 |
| 2025-02 | 851 | 0 | 851 | 21.73 | 58.52 | 54.75 |
| 2025-03 | 901 | 0 | 901 | 21.78 | 61.15 | 58.13 |
| 2025-04 | 1,023 | 0 | 1,023 | 23.62 | 60.90 | 60.25 |
| 2025-05 | 1,004 | 0 | 1,004 | 24.24 | 65.14 | 62.43 |
| 2025-06 | 982 | 0 | 982 | 24.88 | 67.11 | 64.34 |
| 2025-07 | 1,222 | 0 | 1,222 | 26.77 | 72.34 | 68.49 |
| 2025-08 | 1,026 | 0 | 1,026 | 28.54 | 76.61 | 72.11 |
| 2025-09 | 1,020 | 0 | 1,020 | 27.80 | 76.76 | 75.06 |
| 2025-10 | 1,189 | 0 | 1,189 | 29.60 | 80.32 | 78.02 |
| 2025-11 | 940 | 0 | 940 | 31.10 | 82.77 | 79.90 |
| 2025-12 | 1,120 | 0 | 1,120 | 31.88 | 83.84 | 82.24 |
| 2026-01 | 1,177 | 0 | 1,177 | 32.90 | 85.81 | 84.24 |
| 2026-02 | 1,002 | 0 | 1,002 | 33.33 | 88.92 | 86.09 |
| 2026-03 | 1,171 | 0 | 1,171 | 34.57 | 88.81 | 87.79 |
| 2026-04 | 1,190 | 0 | 1,190 | 34.61 | 91.18 | 89.68 |
| 2026-05 | 1,049 | 1 | 1,048 | 36.46 | 92.18 | 90.67 |
| 2026-06 | 1,164 | 10 | 1,154 | 36.42 | 92.63 | 91.98 |
| 2026-07 | 1,271 | 78 | 1,193 | 34.88 | 93.55 | 92.81 |
| 2026-08 | 1,185 | 409 | 776 | 27.51 | 91.75 | 92.76 |
| 2026-09 | 1,251 | 1,101 | 150 | 13.86 | 72.67 | 91.41 |

### Category Spikes

_Peak month per category and the three calendar months with the highest volume (all years combined)._

| category | peak_month | peak_count | monthly_mean | peak_vs_mean | peak_z_score | top_calendar_months |
| --- | --- | --- | --- | --- | --- | --- |
| Other | 2026-06 | 43 | 27.96 | 1.54 | 2.19 | May, Sep, Jun |
| Water - pressure or quality | 2026-05 | 73 | 54.71 | 1.33 | 1.71 | Jul, Jan, May |
| Payment - plan or arrears | 2025-07 | 89 | 66.71 | 1.33 | 1.78 | Jul, Jan, Aug |
| Service - poor communication | 2026-01 | 106 | 79.50 | 1.33 | 2.17 | Sep, Jan, Jul |
| Supply - interruption | 2026-04 | 121 | 91.33 | 1.32 | 1.97 | Jul, Aug, Apr |
| Billing - estimated read | 2026-09 | 258 | 201.38 | 1.28 | 2.23 | Jul, Sep, Aug |
| Metering - no read taken | 2026-07 | 164 | 130.00 | 1.26 | 1.70 | Jul, Apr, Jan |
| Service - missed appointment | 2026-08 | 88 | 71.58 | 1.23 | 1.62 | Jul, Aug, Apr |
| Billing - disputed amount | 2026-09 | 407 | 335.83 | 1.21 | 1.71 | Jul, Sep, Aug |

### Monthly Complaints by Category

| month_year | Billing - disputed amount | Billing - estimated read | Metering - no read taken | Other | Payment - plan or arrears | Service - missed appointment | Service - poor communication | Supply - interruption | Water - pressure or quality |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2024-10 | 306 | 176 | 111 | 32 | 49 | 56 | 70 | 68 | 44 |
| 2024-11 | 260 | 175 | 97 | 18 | 37 | 52 | 54 | 91 | 46 |
| 2024-12 | 312 | 179 | 115 | 17 | 53 | 65 | 72 | 90 | 48 |
| 2025-01 | 305 | 170 | 133 | 30 | 64 | 71 | 78 | 82 | 52 |
| 2025-02 | 281 | 163 | 111 | 17 | 68 | 49 | 57 | 71 | 34 |
| 2025-03 | 276 | 173 | 115 | 26 | 53 | 64 | 74 | 74 | 46 |
| 2025-04 | 319 | 202 | 144 | 22 | 64 | 74 | 76 | 76 | 46 |
| 2025-05 | 342 | 168 | 112 | 37 | 62 | 73 | 78 | 86 | 46 |
| 2025-06 | 320 | 183 | 117 | 26 | 63 | 74 | 72 | 84 | 43 |
| 2025-07 | 386 | 242 | 157 | 24 | 89 | 86 | 88 | 87 | 63 |
| 2025-08 | 319 | 210 | 116 | 24 | 73 | 72 | 73 | 92 | 47 |
| 2025-09 | 294 | 199 | 119 | 31 | 66 | 71 | 99 | 86 | 55 |
| 2025-10 | 378 | 228 | 149 | 24 | 86 | 77 | 82 | 98 | 67 |
| 2025-11 | 298 | 197 | 95 | 25 | 61 | 69 | 73 | 77 | 45 |
| 2025-12 | 355 | 213 | 124 | 27 | 78 | 83 | 71 | 107 | 62 |
| 2026-01 | 352 | 212 | 138 | 34 | 82 | 77 | 106 | 105 | 71 |
| 2026-02 | 305 | 208 | 125 | 20 | 62 | 68 | 76 | 82 | 56 |
| 2026-03 | 384 | 215 | 156 | 31 | 74 | 76 | 92 | 83 | 60 |
| 2026-04 | 368 | 212 | 157 | 31 | 76 | 78 | 79 | 121 | 68 |
| 2026-05 | 349 | 180 | 128 | 33 | 53 | 71 | 76 | 86 | 73 |
| 2026-06 | 368 | 214 | 152 | 43 | 62 | 60 | 93 | 112 | 60 |
| 2026-07 | 400 | 228 | 164 | 34 | 83 | 83 | 91 | 119 | 69 |
| 2026-08 | 376 | 228 | 135 | 26 | 70 | 88 | 86 | 112 | 64 |
| 2026-09 | 407 | 258 | 150 | 39 | 73 | 81 | 92 | 103 | 48 |

## E. Source System Friction

### System Workloads

| source_system | complaints | still_open | share_pct |
| --- | --- | --- | --- |
| SYS-01 | 6,479 | 415 | 25.49 |
| SYS-05 | 6,374 | 433 | 25.08 |
| SYS-03 | 6,282 | 412 | 24.72 |
| SYS-04 | 6,281 | 339 | 24.71 |

### System Efficacy & Friction

_`transfer_days_corr` is the correlation between being transferred and days_to_close within each system. Friction rank 1 = highest transfers and slowest closures combined._

| source_system | complaints | transfer_rate_pct | mean_days | median_days | breach_rate_pct | reopen_rate_pct | transfer_days_corr | friction_rank |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SYS-01 | 6,064 | 46.24 | 30.22 | 27.00 | 78.12 | 18.11 | 0.41 | 1 |
| SYS-03 | 5,870 | 45.59 | 29.41 | 26.00 | 76.87 | 17.90 | 0.37 | 2 |
| SYS-05 | 5,941 | 44.93 | 29.92 | 26.00 | 76.96 | 18.08 | 0.40 | 2 |
| SYS-04 | 5,942 | 0.00 | 23.21 | 22.00 | 69.51 | 9.31 |  | 4 |
