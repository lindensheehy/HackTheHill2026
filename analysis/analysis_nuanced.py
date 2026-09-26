"""Multi-dimensional analysis of the Northwind complaints table in data.db.

Run database_migration/database_migration.py first, then (from any directory):
    python analysis/analysis_nuanced.py

Outputs:
    analysis/analysis_nuanced_report.md  - Markdown report (named so it doesn't overwrite the spec, analysis_nuanced.md)
    data/aggregated_metrics.json         - every aggregated table, for dashboard ingestion
"""

import json
import sqlite3
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "data.db"
TABLE = "northwind_complaints"
REPORT_PATH = REPO_ROOT / "analysis" / "analysis_nuanced_output.md"
METRICS_PATH = REPO_ROOT / "data" / "aggregated_metrics.json"

LONG_TAIL_QUANTILE = 0.99
ROLLING_MONTHS = 3
TOP_ACCOUNTS = 10


# ---------------------------------------------------------------------------
# Loading & preprocessing
# ---------------------------------------------------------------------------

def load_complaints():
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql(f"SELECT * FROM {TABLE}", conn)


def preprocess(df):
    df = df.copy()
    df["date_opened"] = pd.to_datetime(df["date_opened"])
    df["date_closed"] = pd.to_datetime(df["date_closed"])
    df["month_year"] = df["date_opened"].dt.to_period("M").astype(str)

    df["is_open"] = df["status"] == "Open"

    df["bill_correction_value"] = df["bill_correction_value"].fillna(0.0)
    df["has_correction"] = df["bill_correction_value"] > 0

    # resolvable_by_information_only is missing exactly for the open cohort (not yet resolved),
    # so it stays unknown there and is imputed as 0 only for closed tickets.
    closed_missing = ~df["is_open"] & df["resolvable_by_information_only"].isna()
    df.loc[closed_missing, "resolvable_by_information_only"] = 0.0

    threshold = df.loc[~df["is_open"], "days_to_close"].quantile(LONG_TAIL_QUANTILE)
    df["long_tail"] = ~df["is_open"] & (df["days_to_close"] > threshold)
    df.attrs["long_tail_threshold"] = threshold
    return df


def pct(series):
    return series.mean() * 100


# ---------------------------------------------------------------------------
# Analytical modules. Each returns a list of (title, note, DataFrame) sections.
# ---------------------------------------------------------------------------

def data_overview(df):
    closed = df[~df["is_open"]]
    threshold = df.attrs["long_tail_threshold"]
    tail = closed[closed["long_tail"]]

    overview = pd.DataFrame(
        {
            "value": [
                len(df),
                int(df["is_open"].sum()),
                len(closed),
                f"{df['date_opened'].min():%Y-%m-%d} to {df['date_opened'].max():%Y-%m-%d}",
                df["account_id"].nunique(),
                round(threshold, 2),
                len(tail),
            ]
        },
        dtype=object,
        index=pd.Index(name="metric", data=[
            "Total complaints",
            "Open (excluded from resolution/SLA/financial metrics)",
            "Closed (incl. reopened)",
            "Date range (opened)",
            "Distinct accounts",
            f"Long-tail threshold (p{LONG_TAIL_QUANTILE * 100:.0f} days_to_close)",
            "Long-tail complaints",
        ]),
    )

    def share(frame, col):
        return frame[col].value_counts(normalize=True).mul(100)

    profile_rows = []
    for col in ["category", "source_system", "priority"]:
        comp = pd.DataFrame({"long_tail_%": share(tail, col), "all_closed_%": share(closed, col)}).fillna(0)
        comp["over_representation_pp"] = comp["long_tail_%"] - comp["all_closed_%"]
        comp.index = [f"{col}: {v}" for v in comp.index]
        profile_rows.append(comp)
    profile = pd.concat(profile_rows).sort_values("over_representation_pp", ascending=False)

    transfer = pd.DataFrame(
        {
            "subset": ["Long-tail", "All closed"],
            "transferred_%": [pct(tail["transferred_between_systems"]), pct(closed["transferred_between_systems"])],
            "reopened_%": [pct(tail["reopened"]), pct(closed["reopened"])],
            "mean_days_to_close": [tail["days_to_close"].mean(), closed["days_to_close"].mean()],
        }
    ).set_index("subset")

    return [
        ("Dataset Overview", None, overview),
        ("Long-Tail Profile", "Share of long-tail complaints in each segment vs. all closed complaints, "
         "sorted by over-representation (percentage points).", profile.head(12)),
        ("Long-Tail vs. All Closed", None, transfer),
    ]


def sla_performance(df):
    closed = df[~df["is_open"]]

    by_cat_pri = closed.pivot_table(
        index="category", columns="priority", values="sla_breach", aggfunc="mean", margins=True, margins_name="All"
    ).mul(100)
    by_cat_pri = by_cat_pri.sort_values("All", ascending=False)

    transfer = closed.groupby("transferred_between_systems").agg(
        complaints=("complaint_id", "count"),
        mean_days=("days_to_close", "mean"),
        median_days=("days_to_close", "median"),
        breach_rate_pct=("sla_breach", pct),
        reopen_rate_pct=("reopened", pct),
    )
    transfer.index = transfer.index.map({0: "Not transferred", 1: "Transferred"})
    transfer.index.name = "transferred_between_systems"

    target = closed.groupby("sla_days").agg(
        complaints=("complaint_id", "count"),
        mean_days=("days_to_close", "mean"),
        median_days=("days_to_close", "median"),
        p90_days=("days_to_close", lambda s: s.quantile(0.9)),
        breach_rate_pct=("sla_breach", pct),
    )
    target["mean_overrun_days"] = target["mean_days"] - target.index
    target["mean_vs_target_ratio"] = target["mean_days"] / target.index

    regional = closed.groupby("region").agg(
        complaints=("complaint_id", "count"),
        breach_rate_pct=("sla_breach", pct),
        mean_days=("days_to_close", "mean"),
        median_days=("days_to_close", "median"),
    )
    regional["breach_rank"] = regional["breach_rate_pct"].rank(ascending=False, method="min").astype(int)
    regional["days_rank"] = regional["mean_days"].rank(ascending=False, method="min").astype(int)
    regional = regional.sort_values(["breach_rank", "days_rank"])

    return [
        ("Breach Rate (%) by Category & Priority", "Closed complaints only.", by_cat_pri),
        ("System Transfer Penalty", None, transfer),
        ("SLA Target vs. Reality", None, target),
        ("Regional Bottlenecks", "Rank 1 = worst.", regional),
    ]


def financial_impact(df):
    closed = df[~df["is_open"]]
    corrected = closed[closed["has_correction"]]

    totals = pd.DataFrame(
        {
            "value": [
                closed["bill_correction_value"].sum(),
                len(corrected),
                pct(closed["has_correction"]),
                corrected["bill_correction_value"].mean(),
                corrected["bill_correction_value"].median(),
                corrected["bill_correction_value"].max(),
            ]
        },
        dtype=object,
        index=pd.Index(name="metric", data=[
            "Total bill correction value",
            "Complaints with a correction",
            "Share of closed complaints with a correction (%)",
            "Mean correction (where > 0)",
            "Median correction (where > 0)",
            "Largest single correction",
        ]),
    )

    by_category = closed.groupby("category").agg(
        complaints=("complaint_id", "count"),
        corrections=("has_correction", "sum"),
        total_value=("bill_correction_value", "sum"),
    )
    by_category["median_value_where_corrected"] = corrected.groupby("category")["bill_correction_value"].median()
    by_category["share_of_total_pct"] = by_category["total_value"] / by_category["total_value"].sum() * 100
    by_category = by_category.sort_values("total_value", ascending=False)

    accounts = closed.groupby("account_id").agg(
        complaints=("complaint_id", "count"),
        financial_complaints=("has_correction", "sum"),
        total_value=("bill_correction_value", "sum"),
    )
    repeat = pd.DataFrame(
        {
            "accounts": [
                len(accounts),
                int((accounts["complaints"] > 1).sum()),
                int((accounts["financial_complaints"] > 1).sum()),
            ]
        },
        index=pd.Index(name="metric", data=[
            "Accounts with a closed complaint", "Accounts with 2+ complaints", "Accounts with 2+ financial complaints",
        ]),
    )
    top_value = accounts.sort_values("total_value", ascending=False).head(TOP_ACCOUNTS)
    top_volume = accounts.sort_values(["financial_complaints", "total_value"], ascending=False).head(TOP_ACCOUNTS)

    return [
        ("Total Financial Liability", "Closed complaints; missing corrections treated as 0.", totals),
        ("Correction by Category", None, by_category),
        ("Account Repeat Summary", None, repeat),
        (f"Top {TOP_ACCOUNTS} Accounts by Correction Value", None, top_value),
        (f"Top {TOP_ACCOUNTS} Accounts by Financial Complaint Volume",
         "A financial complaint is one with a non-zero bill correction.", top_volume),
    ]


def resolution_efficacy(df):
    closed = df[~df["is_open"]]

    info_only = closed.groupby("resolvable_by_information_only").agg(
        complaints=("complaint_id", "count"),
        reopened=("reopened", "sum"),
        reopen_rate_pct=("reopened", pct),
    )
    info_only.index = info_only.index.map({0.0: "No", 1.0: "Yes"})
    info_only.index.name = "resolvable_by_information_only"

    by_action = closed.groupby("resolution_action").agg(
        complaints=("complaint_id", "count"),
        reopened=("reopened", "sum"),
        reopen_rate_pct=("reopened", pct),
        info_only_resolvable_pct=("resolvable_by_information_only", pct),
    ).sort_values("reopen_rate_pct", ascending=False)

    by_channel = closed.groupby("channel").agg(
        complaints=("complaint_id", "count"),
        info_only_resolvable_pct=("resolvable_by_information_only", pct),
        reopen_rate_pct=("reopened", pct),
        breach_rate_pct=("sla_breach", pct),
    ).sort_values("info_only_resolvable_pct", ascending=False)

    return [
        ("The \"Information Only\" Risk", "Reopen rate split by whether the complaint was resolvable by "
         "information alone.", info_only),
        ("Reopen Rate by Resolution Action", None, by_action),
        ("Channel-Specific Resolution", None, by_channel),
    ]


def time_series(df):
    closed = df[~df["is_open"]]

    monthly = df.groupby("month_year").agg(opened=("complaint_id", "count"), still_open=("is_open", "sum"))
    closed_monthly = closed.groupby("month_year").agg(
        closed=("complaint_id", "count"),
        breaches=("sla_breach", "sum"),
        mean_days=("days_to_close", "mean"),
    )
    monthly = monthly.join(closed_monthly)
    monthly["breach_rate_pct"] = monthly["breaches"] / monthly["closed"] * 100
    rolling = monthly[["breaches", "closed"]].rolling(ROLLING_MONTHS, min_periods=ROLLING_MONTHS).sum()
    monthly[f"rolling_{ROLLING_MONTHS}m_breach_pct"] = rolling["breaches"] / rolling["closed"] * 100
    monthly = monthly.drop(columns="breaches")

    by_category = df.pivot_table(
        index="month_year", columns="category", values="complaint_id", aggfunc="count", fill_value=0
    )

    stats = by_category.agg(["mean", "std", "max"]).T
    spikes = pd.DataFrame(
        {
            "peak_month": by_category.idxmax(),
            "peak_count": stats["max"].astype(int),
            "monthly_mean": stats["mean"],
            "peak_vs_mean": stats["max"] / stats["mean"],
            "peak_z_score": (stats["max"] - stats["mean"]) / stats["std"],
        }
    )
    # Calendar-month seasonality: which months of the year run hottest per category across all years.
    calendar = df.assign(cal_month=df["date_opened"].dt.month).pivot_table(
        index="category", columns="cal_month", values="complaint_id", aggfunc="count", fill_value=0
    )
    spikes["top_calendar_months"] = calendar.apply(
        lambda row: ", ".join(pd.to_datetime(row.nlargest(3).index, format="%m").strftime("%b")), axis=1
    )
    spikes = spikes.sort_values("peak_vs_mean", ascending=False)

    return [
        ("Volume & SLA Degradation by Month",
         f"`breach_rate_pct` and the {ROLLING_MONTHS}-month rolling rate use closed complaints only. "
         "Recent months have more tickets still open, so their closed-only rates skew toward fast resolutions.",
         monthly),
        ("Category Spikes", "Peak month per category and the three calendar months with the highest volume "
         "(all years combined).", spikes),
        ("Monthly Complaints by Category", None, by_category),
    ]


def system_friction(df):
    closed = df[~df["is_open"]]

    workload = df.groupby("source_system").agg(
        complaints=("complaint_id", "count"),
        still_open=("is_open", "sum"),
    )
    workload["share_pct"] = workload["complaints"] / workload["complaints"].sum() * 100
    workload = workload.sort_values("complaints", ascending=False)

    efficacy = closed.groupby("source_system").agg(
        complaints=("complaint_id", "count"),
        transfer_rate_pct=("transferred_between_systems", pct),
        mean_days=("days_to_close", "mean"),
        median_days=("days_to_close", "median"),
        breach_rate_pct=("sla_breach", pct),
        reopen_rate_pct=("reopened", pct),
    )
    # Undefined (blank) for a system that never, or always, transfers.
    efficacy["transfer_days_corr"] = closed.groupby("source_system").apply(
        lambda g: g["transferred_between_systems"].corr(g["days_to_close"])
        if g["transferred_between_systems"].nunique() > 1 else float("nan"),
        include_groups=False,
    )
    # Composite friction: average of the transfer-rate rank and closure-time rank (1 = most friction).
    efficacy["friction_rank"] = (
        efficacy["transfer_rate_pct"].rank(ascending=False) + efficacy["mean_days"].rank(ascending=False)
    ).rank(method="min").astype(int)
    efficacy = efficacy.sort_values("friction_rank")

    return [
        ("System Workloads", None, workload),
        ("System Efficacy & Friction", "`transfer_days_corr` is the correlation between being transferred and "
         "days_to_close within each system. Friction rank 1 = highest transfers and slowest closures combined.",
         efficacy),
    ]


# ---------------------------------------------------------------------------
# Key takeaways, derived from the computed tables
# ---------------------------------------------------------------------------

def key_takeaways(df, results):
    t = {title: table for sections in results.values() for title, _, table in sections}
    out = []

    cat_pri = t["Breach Rate (%) by Category & Priority"].drop(index="All").drop(columns="All")
    worst_cat, worst_pri = cat_pri.stack().idxmax()
    out.append(f"**Worst SLA cell:** {worst_cat} at {worst_pri} breaches "
               f"{cat_pri.loc[worst_cat, worst_pri]:.1f}% of the time.")

    tr = t["System Transfer Penalty"]
    no, yes = tr.loc["Not transferred"], tr.loc["Transferred"]
    out.append(f"**Transfer penalty:** transferred tickets take {yes['mean_days']:.1f} days on average vs "
               f"{no['mean_days']:.1f} ({yes['mean_days'] / no['mean_days']:.2f}x), with a breach rate of "
               f"{yes['breach_rate_pct']:.1f}% vs {no['breach_rate_pct']:.1f}%.")

    target = t["SLA Target vs. Reality"]
    worst_sla = target["mean_vs_target_ratio"].idxmax()
    out.append(f"**SLA reality gap:** the {worst_sla}-day SLA cohort averages "
               f"{target.loc[worst_sla, 'mean_days']:.1f} days "
               f"({target.loc[worst_sla, 'mean_vs_target_ratio']:.2f}x target).")

    region = t["Regional Bottlenecks"].iloc[0]
    out.append(f"**Regional bottleneck:** {region.name} has the highest breach rate "
               f"({region['breach_rate_pct']:.1f}%, mean {region['mean_days']:.1f} days).")

    fin = t["Correction by Category"]
    liability = t["Total Financial Liability"].loc["Total bill correction value", "value"]
    out.append(f"**Financial liability:** {liability:,.2f} in bill corrections; {fin.index[0]} accounts for "
               f"{fin.iloc[0]['share_of_total_pct']:.1f}% ({fin.iloc[0]['total_value']:,.2f}).")

    repeat = t["Account Repeat Summary"]["accounts"]
    out.append(f"**Repeat accounts:** {repeat['Accounts with 2+ complaints']:,} of "
               f"{repeat['Accounts with a closed complaint']:,} accounts have more than one closed complaint; "
               f"{repeat['Accounts with 2+ financial complaints']:,} have more than one financial complaint.")

    info = t["The \"Information Only\" Risk"]
    out.append(f"**Information-only risk:** complaints resolvable by information alone reopen at "
               f"{info.loc['Yes', 'reopen_rate_pct']:.1f}% vs {info.loc['No', 'reopen_rate_pct']:.1f}% for the rest.")

    action = t["Reopen Rate by Resolution Action"].iloc[0]
    out.append(f"**Least durable fix:** \"{action.name}\" reopens {action['reopen_rate_pct']:.1f}% of the time.")

    channel = t["Channel-Specific Resolution"].iloc[0]
    out.append(f"**Channel:** {channel.name} has the highest information-only resolvable rate "
               f"({channel['info_only_resolvable_pct']:.1f}%).")

    monthly = t["Volume & SLA Degradation by Month"]
    rolling_col = f"rolling_{ROLLING_MONTHS}m_breach_pct"
    rolling = monthly[rolling_col].dropna()
    out.append(f"**SLA trend:** the {ROLLING_MONTHS}-month rolling breach rate moved from {rolling.iloc[0]:.1f}% "
               f"({rolling.index[0]}) to {rolling.iloc[-1]:.1f}% ({rolling.index[-1]}), peaking at "
               f"{rolling.max():.1f}% in {rolling.idxmax()}.")

    spike = t["Category Spikes"].iloc[0]
    out.append(f"**Sharpest spike:** {spike.name} peaked at {spike['peak_count']} in {spike['peak_month']} "
               f"({spike['peak_vs_mean']:.2f}x its monthly mean); busiest calendar months: "
               f"{spike['top_calendar_months']}.")

    system = t["System Efficacy & Friction"].iloc[0]
    out.append(f"**Highest-friction system:** {system.name} "
               f"({system['transfer_rate_pct']:.1f}% transferred, mean {system['mean_days']:.1f} days to close).")

    return out


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def fmt(value):
    if isinstance(value, float):
        return "" if pd.isna(value) else f"{value:,.2f}"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    return str(value)


def md_table(table):
    table = table.reset_index()
    header = [str(c) for c in table.columns]
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    for row in table.itertuples(index=False):
        lines.append("| " + " | ".join(fmt(v.item() if hasattr(v, "item") else v) for v in row) + " |")
    return "\n".join(lines)


def write_report(results, takeaways):
    lines = [
        "# Northwind Complaints: Nuanced Analysis",
        "",
        f"Generated from `data/{DB_PATH.name}` (table `{TABLE}`) by `analysis/analysis_nuanced.py`.",
        "",
        "## Key Takeaways",
        "",
        *[f"- {line}" for line in takeaways],
        "",
    ]
    for module, sections in results.items():
        lines += [f"## {module}", ""]
        for title, note, table in sections:
            lines += [f"### {title}", ""]
            if note:
                lines += [f"_{note}_", ""]
            lines += [md_table(table), ""]
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_metrics(results, takeaways):
    payload = {"key_takeaways": takeaways}
    for module, sections in results.items():
        payload[module] = {
            title: json.loads(table.reset_index().to_json(orient="records")) for title, _, table in sections
        }
    with open(METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def main():
    df = preprocess(load_complaints())

    results = {
        "Data Preparation & Long-Tail": data_overview(df),
        "A. SLA Performance & Bottlenecks": sla_performance(df),
        "B. Financial Impact (Bill Corrections)": financial_impact(df),
        "C. Reopen Rate & Resolution Efficacy": resolution_efficacy(df),
        "D. Time-Series & Trends": time_series(df),
        "E. Source System Friction": system_friction(df),
    }
    takeaways = key_takeaways(df, results)

    write_report(results, takeaways)
    write_metrics(results, takeaways)
    print(f"Success! Report written to {REPORT_PATH}, metrics to {METRICS_PATH}")


if __name__ == "__main__":
    main()
