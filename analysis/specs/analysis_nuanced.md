# Specification: Northwind Complaints Advanced Database Analysis Script

## 1. Overview
This script will perform a nuanced, multi-dimensional analysis on the Northwind complaints dataset. Rather than reading from raw CSVs, this script must connect to the local SQLite database (`./data.db`) and query the `northwind_complaints` table (referencing `./schema.md` for exact data types). The goal is to uncover operational bottlenecks, financial impacts, system inefficiencies, and customer friction points through cross-tabulations, aggregations, and time-based metrics. 

## 2. Data Source & Schema
The script must connect to `./data.db` and query the `northwind_complaints` table. It should expect and handle the following schema structure:

*   **`complaint_id`**: String/Text (Unique Identifier)
*   **`account_id`**: String/Text (Customer/Account Identifier)
*   **`date_opened`**: Datetime/Text 
*   **`date_closed`**: Datetime/Text (Nullable for open cases)
*   **`status`**: String/Text (e.g., Open, Closed, Closed - reopened)
*   **`channel`**: String/Text (Origin channel: Phone, Web form, Email, etc.)
*   **`category`**: String/Text (Nature of complaint)
*   **`priority`**: String/Text (P1, P2, P3)
*   **`region`**: String/Text (Geographic area)
*   **`source_system`**: String/Text (Originating IT system)
*   **`transferred_between_systems`**: Boolean/Integer (0 or 1 - indicates if the ticket crossed systems)
*   **`sla_days`**: Integer (Target days to close: 5, 10, 20)
*   **`days_to_close`**: Float/Integer (Actual time taken; Nullable)
*   **`sla_breach`**: Boolean/Integer (0 or 1 - indicates if `days_to_close` > `sla_days`)
*   **`reopened`**: Boolean/Integer (0 or 1)
*   **`resolution_action`**: String/Text (What was done to fix it; Nullable)
*   **`resolvable_by_information_only`**: Boolean/Float (0.0, 1.0; Nullable)
*   **`bill_correction_value`**: Float/Real (Financial value of correction; Nullable/Zero)

## 3. Data Cleaning & Preprocessing Requirements
Whether handled via SQL queries during extraction or in-memory using Pandas post-extraction, the script must perform the following:
1.  **Datetime Conversion**: Ensure `date_opened` and `date_closed` are treated as native datetime objects. Calculate an explicit `month_year` dimension for time-series grouping.
2.  **Handling Open Tickets**: Filter out or segment tickets with `status == 'Open'` when calculating resolution times, SLA breaches, and financial impacts to avoid skewed averages.
3.  **Missing Value Imputation**: Treat missing `bill_correction_value` as `0.0`. Treat missing `resolvable_by_information_only` as `False/0` unless tied to a specific missing cohort.
4.  **Outlier Detection**: Flag complaints in the top 1% of `days_to_close` as a separate "Long-Tail" subset.

## 4. Analytical Modules (Exhaustive)

The script should execute the following analyses and compile the results:

### A. SLA Performance & Bottleneck Analysis
*   **Breach Rate by Category & Priority**: Calculate the percentage of SLA breaches for each complaint category, segmented by priority level. 
*   **System Transfer Penalty**: Compare the mean/median `days_to_close` and SLA breach rate for tickets where `transferred_between_systems == 1` versus `0`.
*   **SLA Target vs. Reality**: For each `sla_days` cohort (5, 10, 20), what is the actual average `days_to_close`? 
*   **Regional Bottlenecks**: Rank regions by their SLA breach rates and average `days_to_close`.

### B. Financial Impact (Bill Corrections)
*   **Total Financial Liability**: Calculate the sum of `bill_correction_value` across the entire dataset.
*   **Correction by Category**: Group total and median `bill_correction_value` by `category`. Which complaint type costs the company the most in corrections?
*   **Account Repeat Offenders**: Group by `account_id` to find accounts with the highest aggregate `bill_correction_value` or highest volume of financial complaints. 

### C. Reopen Rate & Resolution Efficacy
*   **The "Information Only" Risk**: Calculate the `reopened` rate for tickets where `resolvable_by_information_only == 1` vs `0`. Does providing only information result in higher customer pushback?
*   **Reopen Rate by Resolution Action**: Cross-tabulate `resolution_action` against the `reopened` flag. Which actions (e.g., "Payment plan amended", "Information provided only") have the highest failure/reopen rates?
*   **Channel-Specific Resolution**: Which `channel` has the highest rate of `resolvable_by_information_only`? 

### D. Time-Series & Trend Analysis
*   **Volume Over Time**: Monthly aggregate count of `date_opened`.
*   **SLA Degradation**: Track the SLA breach rate on a monthly rolling basis to see if performance is deteriorating.
*   **Category Spikes**: Monthly count of complaints grouped by `category` to identify seasonal spikes (e.g., do "Billing - estimated read" complaints spike in specific months?).

### E. Source System Friction
*   **System Workloads**: Breakdown of total volume by `source_system`.
*   **System Efficacy**: Correlate `source_system` with `transferred_between_systems` and `days_to_close`. Which system generates the most friction (highest transfers and slowest closures)?

## 5. Output Specifications
The script should output the results in a structured format, generating two artifacts:
1.  **`analysis_nuanced.md`**: A stylized Markdown report containing summary tables, key takeaways, and the calculated metrics for all modules listed in Section 4.
2.  **`aggregated_metrics.json`** (Optional): A structured data export containing the raw aggregated dataframes/dictionaries for potential dashboard ingestion.