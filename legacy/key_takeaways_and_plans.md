# Northwind Complaints: Key Takeaways & Proposed Solutions

Sources: [analysis/analysis_nuanced_output.md](analysis/analysis_nuanced_output.md), plus the unit-cost, systems, KPI, meter-read and AI-pilot CSVs.
Money is shown in £. The data doesn't name a currency, but the regulator and cost model look UK-style.

## The situation in one paragraph

Performance has been getting steadily worse for two years. It isn't seasonal. Monthly complaints are up 37% (912 → 1,251). Average days to close went from 9 to 38. The SLA breach rate went from 44% to about 92%. First-contact resolution fell from 62% to 41%, and the regulator satisfaction score fell from 4.3 to 2.6. Enhanced regulator monitoring is estimated at **£2.4M per quarter**, which is the biggest financial risk in the data.

## What stands out

1. **Transfers between systems are the main driver of bad outcomes.** About a third of complaints are transferred.
   - Transferred tickets take 38 days vs 23, breach SLA 88% vs 69% of the time, and **reopen 29% vs 9%**.
   - They cost £121 each vs £68.
   - **Every one of the slowest 1% of tickets was a transfer.**
   - CaseTrack (SYS-04) never transfers a case, and it's the fastest system at 23 days.
   - The systems file explains why transfers hurt: "Cases transferred in… lose their history", "Agents run four systems side by side", and field engineers "arrive without the complaint history".

2. **Priority labels aren't changing the outcome.** Every SLA tier finishes about **1.7x over target**. The breach rate is about the same for P1 (72%), P2 (75%) and P3 (76%). High-priority tickets close sooner, but they still miss their deadline just as often.

3. **Two regions produce a large share of the billing pain.**
   - Barrowdale and Dunmoor have **0% smart meters**, about 60% estimated reads (vs about 22% elsewhere), and about 2x the billing exceptions.
   - They are 2 of 6 regions but produce **46% of the £1.35M in bill corrections**.
   - Both run on Aurora Billing (SYS-01, COBOL, two developers left) and MeterHub (SYS-06), whose estimation algorithm hasn't changed since 2012 and has no feedback loop from corrected bills.
   - Across all regions, billing and metering account for about 63% of complaints and all of the bill-correction value.

4. **About a quarter of complaints only need information.** 24% of closed complaints were "resolvable by information only", roughly 3,000 a year. They reopen no more often than other complaints (16.2% vs 15.7%), so information is enough for them. The problem is that they use the full complaint process, at £68 each.

5. **The AI chatbot pilot got worse the longer it ran.** Over nine months:
   - The share of sessions it resolved fully fell from 16% to 10%.
   - Repeat contact within 7 days rose from 31% to 45%.
   - Customer satisfaction fell from 2.6 to 2.0.
   - It cost £640k a year and has been paused.

   **Pitching "another chatbot" is a weak position.** A pitch built on structured data and simple statistical models fits better, and it's cheaper.

6. **The spikes and repeat customers are small.**
   - No category peaks above about 1.5x its monthly average.
   - Almost no account complains more than once: 291 of 23.5k accounts.
   - The problem is structural (systems and processes), not a small group of problem accounts or seasonal peaks.

7. **The open backlog is already late.** 1,599 complaints are open, and 98% have already breached SLA, including 35 at P1.

## Proposed solutions

Costs are rough, order-of-magnitude estimates for scoping, not quotes. Savings use Northwind's own unit costs from the last 12 months.

### 1. Intake triage & routing engine ⭐ core demo
- **What:** a scoring service that runs when a complaint arrives. It predicts:
  - which system or team should own the complaint, so it's routed right the first time;
  - the risk of a transfer;
  - the risk of an SLA breach;
  - whether information alone is likely to resolve it.
- **Software:** Python service with gradient-boosted or logistic models trained on complaint history (category, channel, region, system, meter-read signals). It exposes a REST API to CallCentre One and CaseTrack, and has a simple triage dashboard. No LLM.
- **Cost:** about £150–250k to build (small team, around 3 months) and about £40–60k a year to run.
- **Value:** 4,800 transfers a year × £53 extra cost each = about **£250k a year**. Halving transfers saves about £125k a year and should also bring down the reopen rate and time to close.

### 2. Backlog clearance & SLA-risk queue ⭐ quick win
- **What:** a daily-ranked work queue for open and new cases, ordered by breach risk, priority and age. It includes staffing what-if planning, e.g. "at X more staff, the backlog clears by date Y".
- **Software:** a web dashboard reading from the database, with the risk scores from #1 and a simple queue-capacity simulation.
- **Cost:** about £30–60k, delivered in a few weeks.
- **Value:** moves the breach curve, which is the metric the regulator watches.

### 3. "Connect the dots" early-warning monitor ⭐ fits our premise
- **What:** combines complaints, meter reads, billing exceptions and outage data by region, system and month. It flags unusual changes, links them to the systems they share, and opens an investigation card with the evidence.
  - Example: estimated-read complaints rising in Barrowdale and Dunmoor, with SYS-01 and SYS-06 as the common link.
- **Software:** a scheduled statistics pipeline (rolling z-scores and change-point detection), a region-to-system dependency graph, and an alerts and investigation board.
- **Cost:** about £80–150k to build and about £30k a year to run.
- **Value:** catches problems like the Barrowdale/Dunmoor metering issue months earlier. It also shows where to direct investment, for example which meters to replace first.

### 4. Proactive information & self-service (not a chatbot)
- **What:** targets the roughly 25% of complaints that only need information, before they become complaints:
  - a bill breakdown in the Northwind Connect self-service app (it can't show one today);
  - messaging that explains an estimated read when it happens;
  - outage-aware suppression of billing reminders, using data from the outage monitoring system (GridWatch).
- **Software:** Northwind Connect front-end features, an event-triggered SMS/email service, and a hook from GridWatch into billing communications.
- **Cost:** about £100–200k.
- **Value:** if half of the roughly 3,000 information-only complaints a year are avoided: about £100k a year in handling, plus fewer inbound calls at £7.40 each. It also costs far less than the £640k chatbot.

### 5. Unified case history / integration layer (bigger roadmap item)
- **What:** one case record that moves with the complaint across CaseTrack, CallCentre One, FieldForce and DocVault. Transfers become handoffs that keep the full history, not re-entry.
- **Software:** an event bus plus a case-history service with API connectors, replacing the nightly batch files. It lines up with the Helix CIS replacement, which has to happen within 18 months anyway because vendor support ends.
- **Cost:** about £400–800k to build and about £100–150k a year to run.
- **Value:** targets the transfer penalty at its root: time to close, the 29% reopen rate and the extra £53 per transfer. It works well together with #1.

### 6. Targeted metering fix for Barrowdale & Dunmoor (capital decision support)
- **What:** add a feedback loop so corrected bills improve MeterHub's estimates, then roll out smart meters in phases, starting with the accounts that raise the most exceptions.
- **Cost:** a full rollout is 519k accounts × £148, about **£77M**, which is why it's been deferred twice. A targeted first phase of about 50k high-exception meters is about £7–8M. Tuning the estimation feedback loop is about £100–200k.
- **Value:** these two regions produce about £620k a year in corrections, and billing complaints are the largest category overall.

## Suggested pitch

Lead with **#1 + #2 + #3** as one product: a low-cost, non-LLM triage and early-warning platform. It's demonstrable, costs well under £0.5M to build, and directly addresses the three worst trends: transfers, SLA breaches and the regulator score. Present **#4–#6** as the roadmap it justifies, with #3's dependency graph as the evidence behind each investment.
