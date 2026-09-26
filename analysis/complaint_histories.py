#!/usr/bin/env python3
"""Tell evidence-based complaint histories using CSV or SQLite; Python 3.9+, no packages.

Copy into the repository's analysis/ directory and run:
    python analysis/complaint_histories.py
    python analysis/complaint_histories.py --window-days 60 --account ACC-951525

Outputs a concise Markdown report and JSON suitable for a dashboard. No AI calls.
"""

import argparse
import csv
import hashlib
import itertools
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


REQUIRED = {
    "complaint_id", "account_id", "date_opened", "date_closed", "status",
    "category", "region", "reopened", "resolution_action",
}
CLOSED_STATUSES = {"Closed", "Closed - reopened"}


def parse_date(value):
    """Accept CSV dates and the midnight datetime strings stored by pandas in SQLite."""
    return date.fromisoformat(str(value)[:10]) if value not in (None, "") else None


def load_cases(source, source_kind):
    source = Path(source).resolve()
    if source_kind == "db":
        # Read-only connection: never migrate, modify or create the user's database.
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            raw = [dict(r) for r in conn.execute("SELECT * FROM northwind_complaints")]
            columns = set(raw[0]) if raw else set()
    else:
        with source.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            columns = set(reader.fieldnames or [])
            raw = list(reader)
    if not raw:
        raise ValueError("The complaints input has no records.")
    missing = REQUIRED - columns
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(sorted(missing)))
    cases, ids = [], set()
    for number, row in enumerate(raw, 2):
        row = {k: v.strip() if isinstance(v, str) else v for k, v in row.items()}
        try:
            for key in ("complaint_id", "account_id", "category", "region"):
                if not row.get(key):
                    raise ValueError("blank " + key)
            if row["complaint_id"] in ids:
                raise ValueError("duplicate complaint_id " + row["complaint_id"])
            ids.add(row["complaint_id"])
            row["date_opened"] = parse_date(row["date_opened"])
            row["date_closed"] = parse_date(row["date_closed"])
            if row["date_opened"] is None:
                raise ValueError("blank date_opened")
            if row["status"] not in CLOSED_STATUSES | {"Open"}:
                raise ValueError("unsupported status " + str(row["status"]))
            row["recorded_closed"] = row["status"] in CLOSED_STATUSES
            if row["recorded_closed"] != (row["date_closed"] is not None):
                raise ValueError("status and date_closed disagree")
            if row["date_closed"] and row["date_closed"] < row["date_opened"]:
                raise ValueError("date_closed precedes date_opened")
            row["reopened"] = int(float(row["reopened"]))
            if row["reopened"] not in (0, 1):
                raise ValueError("reopened must be 0 or 1")
            for key in ("transferred_between_systems", "sla_breach", "sla_days"):
                row[key] = int(float(row[key])) if row.get(key) not in (None, "") else None
            value = row.get("bill_correction_value")
            row["bill_correction_value"] = float(value) if value not in (None, "") else None
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError("Invalid input at record {}: {}".format(number, exc)) from exc
        cases.append(row)
    return sorted(cases, key=lambda r: (r["account_id"], r["date_opened"], r["complaint_id"]))


def relationship(first, second):
    """Transparent investigation rules; none establishes a common root cause."""
    if first == second:
        return "same_category"
    if first == "Metering - no read taken" and second.startswith("Billing -"):
        return "metering_to_billing"
    if first == "Billing - estimated read" and second == "Billing - disputed amount":
        return "estimated_read_to_disputed_bill"
    return "different_category"


def public_case(case):
    fields = (
        "complaint_id", "date_opened", "date_closed", "category", "region", "status",
        "resolution_action", "reopened", "bill_correction_value", "source_system",
        "priority", "transferred_between_systems", "sla_breach",
    )
    return {k: case.get(k) for k in fields}


def analyse(cases, window_days=90, snapshot_date=None):
    if window_days < 1:
        raise ValueError("window_days must be positive")
    last_date = max(max(r["date_opened"], r["date_closed"] or r["date_opened"]) for r in cases)
    snapshot = snapshot_date or last_date
    if snapshot < last_date:
        raise ValueError("Snapshot precedes recorded events. This extract cannot reconstruct past statuses.")
    by_account = defaultdict(list)
    for case in cases:
        by_account[case["account_id"]].append(case)
    for history in by_account.values():
        history.sort(key=lambda r: (r["date_opened"], r["complaint_id"]))
    multi_region = {a for a, h in by_account.items() if len({r["region"] for r in h}) > 1}
    pairs, cross_region = [], []
    pair_flags = Counter()
    # Compare ALL earlier cases, so an unrelated intervening case cannot hide a candidate.
    for account, history in by_account.items():
        for first, second in itertools.combinations(history, 2):
            if second["date_opened"] == first["date_opened"]:
                pair_flags["pairs_opened_same_day_order_unknown"] += 1
                continue
            if first["date_closed"] is None or second["date_opened"] < first["date_closed"]:
                pair_flags["pairs_with_earlier_case_still_open"] += 1
                continue
            gap = (second["date_opened"] - first["date_closed"]).days
            if gap == 0:
                pair_flags["pairs_on_closure_day_order_unknown"] += 1
                continue
            if gap > window_days:
                pair_flags["post_closure_pairs_beyond_window"] += 1
                continue
            pair = {
                "account_id": account,
                "first_complaint_id": first["complaint_id"],
                "later_complaint_id": second["complaint_id"],
                "first_category": first["category"],
                "later_category": second["category"],
                "first_region": first["region"], "later_region": second["region"],
                "first_closed": first["date_closed"], "later_opened": second["date_opened"],
                "days_after_closure": gap,
                "first_recorded_action": first["resolution_action"],
                "relationship": relationship(first["category"], second["category"]),
                "account_has_multiple_regions": account in multi_region,
                "first_case_has_full_followup_window": (snapshot - first["date_closed"]).days >= window_days,
            }
            (pairs if first["region"] == second["region"] else cross_region).append(pair)
    pairs.sort(key=lambda p: (p["account_id"], p["first_closed"], p["later_opened"]))
    followed_ids = {p["first_complaint_id"] for p in pairs}
    pairs_by_first = defaultdict(list)
    for p in pairs:
        pairs_by_first[p["first_complaint_id"]].append(p)

    def summarize(rows, label, kind):
        accounts = {r["account_id"] for r in rows}
        opened_accounts = {r["account_id"] for r in rows if not r["recorded_closed"]}
        closed = [r for r in rows if r["recorded_closed"]]
        eligible = [r for r in closed if (snapshot - r["date_closed"]).days >= window_days]
        group_pairs = [p for r in rows for p in pairs_by_first[r["complaint_id"]]]
        eligible_with_followup = sum(r["complaint_id"] in followed_ids for r in eligible)
        result = {
            "group": label, "group_type": kind, "unique_accounts": len(accounts),
            "complaints": len(rows), "recorded_closed_cases": len(closed),
            "open_cases": len(rows) - len(closed),
            "accounts_with_a_closed_case": len({r["account_id"] for r in closed}),
            "accounts_all_cases_in_group_closed": len(accounts - opened_accounts),
            "accounts_with_an_open_case": len(opened_accounts),
            "reopened_cases": sum(r["reopened"] for r in rows),
            "followup_accounts": len({p["account_id"] for p in group_pairs}),
            "earlier_cases_with_followup": len({p["first_complaint_id"] for p in group_pairs}),
            "distinct_later_cases": len({p["later_complaint_id"] for p in group_pairs}),
            "matched_followup_pairs": len(group_pairs),
            "closed_cases_with_full_window": len(eligible),
            "full_window_cases_with_followup": eligible_with_followup,
            "full_window_followup_rate_pct": round(100 * eligible_with_followup / len(eligible), 3) if eligible else None,
            "closed_cases_without_full_window": len(closed) - len(eligible),
        }
        scope = "Across this dataset" if kind == "overall" else (
            "For {}".format(label) if kind in {"category", "region_category"} else "In {}".format(label))
        def count(n, noun):
            return "{:,} {}{}".format(n, noun, "" if n == 1 else "s")
        followups = result["followup_accounts"]
        reopenings = result["reopened_cases"]
        open_count = len(rows) - len(closed)
        result["story"] = (
            f"{scope}, {count(len(accounts), 'distinct account')} raised {count(len(rows), 'complaint')}. "
            f"{count(len(closed), 'case')} {'was' if len(closed) == 1 else 'were'} marked closed; "
            f"{count(open_count, 'case')} {'remains' if open_count == 1 else 'remain'} open. "
            f"All cases in this group are marked closed for {count(result['accounts_all_cases_in_group_closed'], 'account')}; "
            f"{count(len(opened_accounts), 'account')} {'has' if len(opened_accounts) == 1 else 'have'} an open case in this group. "
            f"{count(followups, 'account')} later raised another complaint in the same region within {window_days} days "
            f"after a case in this group was closed. Separately, {count(reopenings, 'case')} "
            f"{'carries' if reopenings == 1 else 'carry'} a reopened flag."
        )
        return result

    def groups(field):
        grouped = defaultdict(list)
        for row in cases:
            grouped[row[field]].append(row)
        return [summarize(rows, name, field) for name, rows in sorted(grouped.items())]

    region_categories = defaultdict(list)
    for row in cases:
        region_categories[(row["region"], row["category"])].append(row)
    region_category_rows = []
    for (region, category), rows in sorted(region_categories.items()):
        item = summarize(rows, category + " in " + region, "region_category")
        item.update({"region": region, "category": category})
        region_category_rows.append(item)

    transitions = defaultdict(list)
    for p in pairs:
        transitions[(p["first_category"], p["later_category"])].append(p)
    transition_rows = []
    for (first, later), items in transitions.items():
        transition_rows.append({
            "first_category": first, "later_category": later,
            "relationship": relationship(first, later), "pairs": len(items),
            "unique_accounts": len({p["account_id"] for p in items}),
            "earlier_cases": len({p["first_complaint_id"] for p in items}),
            "later_cases": len({p["later_complaint_id"] for p in items}),
            "minimum_days_after_closure": min(p["days_after_closure"] for p in items),
            "maximum_days_after_closure": max(p["days_after_closure"] for p in items),
            "account_ids": sorted({p["account_id"] for p in items}),
        })
    transition_rows.sort(key=lambda r: (-r["unique_accounts"], r["first_category"], r["later_category"]))
    account_pairs = defaultdict(list)
    for p in pairs:
        account_pairs[p["account_id"]].append(p)
    histories = []
    for account, history in sorted(by_account.items()):
        if len(history) < 2:
            continue
        histories.append({
            "account_id": account, "complaint_count": len(history),
            "regions": sorted({r["region"] for r in history}),
            "region_change_warning": account in multi_region,
            "events": [public_case(r) for r in history], "followup_pairs": account_pairs[account],
        })
    overview = summarize(cases, "All complaints", "overall")
    overview.update({
        "accounts_with_multiple_complaints": sum(len(h) > 1 for h in by_account.values()),
        "complaints_on_repeat_accounts": sum(len(h) for h in by_account.values() if len(h) > 1),
        "extra_complaints_beyond_first_per_account": len(cases) - len(by_account),
        "accounts_with_records_in_multiple_regions": len(multi_region),
        "max_complaints_per_account": max(map(len, by_account.values())),
    })
    return {
        "metadata": {
            "snapshot_date": snapshot, "snapshot_date_inferred": snapshot_date is None,
            "first_opening_date": min(r["date_opened"] for r in cases),
            "last_opening_date": max(r["date_opened"] for r in cases),
            "window_days": window_days,
            "followup_definition": "Same account and same region; a distinct later complaint opens 1..window_days after the earlier recorded closure. All earlier/later pairs are considered.",
            "population": "Accounts represented in this extract, not all Northwind customers or individual people.",
            "rate_definition": "Distinct earlier closed cases with a matched follow-up / closed cases with a complete observation window. Counts include observed follow-ups even when the full window is not yet available.",
            "limitations": [
                "Recorded closure does not prove the underlying issue was fixed.",
                "A later complaint is a candidate follow-up, not proof of a shared cause.",
                "Reopened is a flag on one complaint; no reopening timestamps or event history are provided.",
                "Different-region pairs are excluded from main follow-up metrics and retained separately.",
                "An account with a same-region pair may still have other records in another region; its full timeline is flagged.",
                "Accounts can appear in multiple category/region rows; group counts are not additive.",
                "A region/category follow-up count is attributed to the EARLIER complaint; the later complaint can have a different category.",
                "Meter visit required or field repair required does not establish that the visit or repair was completed.",
                "The inferred snapshot date is the latest recorded opening/closure. Specify the actual extract date if known.",
            ],
        },
        "overview": overview, "by_category": groups("category"), "by_region": groups("region"),
        "by_region_category": region_category_rows,
        "transitions": transition_rows, "followup_pairs": pairs,
        "excluded_cross_region_pairs": cross_region,
        "sequence_flags": dict(pair_flags), "repeat_account_histories": histories,
    }


def md_table(headers, rows):
    def cell(value):
        if value is None:
            return "Not recorded"
        return str(value).replace("|", "\\|").replace("\n", " ")
    return "\n".join([
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
        *["| " + " | ".join(cell(v) for v in row) + " |" for row in rows],
    ])


def report(result, cases, examples=3, account=None):
    m, o = result["metadata"], result["overview"]
    window = m["window_days"]
    lines = [
        "# Northwind complaint histories", "",
        "Snapshot: **{}**{}. Follow-up window: **{} days**.".format(
            m["snapshot_date"], " (inferred from the latest recorded event)" if m["snapshot_date_inferred"] else "", window),
        "", o["story"], "",
        "Here, an account is an account ID, not necessarily a person. 'Closed' means recorded as closed, not independently verified as fixed.", "",
        "## How much repeat contact is visible?", "",
        md_table(["Measure", "Count"], [
            ["Distinct accounts", f"{o['unique_accounts']:,}"],
            ["Accounts with multiple complaint records", f"{o['accounts_with_multiple_complaints']:,}"],
            ["Accounts appearing in multiple regions", f"{o['accounts_with_records_in_multiple_regions']:,}"],
            ["Accounts with an observed same-region follow-up within the window", f"{o['followup_accounts']:,}"],
            ["Matched earlier/later complaint pairs", f"{o['matched_followup_pairs']:,}"],
            ["Distinct later complaints in those pairs", f"{o['distinct_later_cases']:,}"],
            ["Cases marked reopened (a separate measure)", f"{o['reopened_cases']:,}"],
        ]), "",
        "A follow-up must open strictly AFTER the earlier recorded closure. Same-day ordering is unknown. Different-region pairs are excluded from these follow-up counts.", "",
        "## Stories by complaint category", "",
    ]
    for row in result["by_category"]:
        lines += [row["story"], ""]
    lines += ["## Stories by region", ""]
    for row in result["by_region"]:
        lines += [row["story"], ""]
        biggest = max((r for r in result["by_region_category"] if r["region"] == row["group"]), key=lambda r: r["complaints"])
        lines += ["Its largest category is **{}**: {:,} accounts, {:,} complaints, {:,} marked closed and {:,} still open. All region/category combinations are in the JSON output.".format(
            biggest["category"], biggest["unique_accounts"], biggest["complaints"], biggest["recorded_closed_cases"], biggest["open_cases"]), ""]
    lines += [
        "Accounts may appear in several groups. An account can have both closed and open cases. 'All cases closed' applies only to cases inside the stated group.", "",
        "## What came after a recorded closure?", "",
        "These are observed category sequences, not verified causal links. Counts refer to account IDs and matched pairs.", "",
        md_table(["Earlier category", "Later category", "Accounts", "Pairs", "Days after closure"], [
            [r["first_category"], r["later_category"], r["unique_accounts"], r["pairs"],
             str(r["minimum_days_after_closure"]) if r["minimum_days_after_closure"] == r["maximum_days_after_closure"] else "{}–{}".format(r["minimum_days_after_closure"], r["maximum_days_after_closure"])]
            for r in result["transitions"]
        ]) if result["transitions"] else "No same-account, same-region follow-ups matched this window.", "",
        "## Follow-up rates with enough time to observe them", "",
        "Recent closures have not had a full {} days to produce a follow-up. The rate below excludes those incomplete windows; an observed follow-up still appears in the counts above.".format(window), "",
        md_table(["Category", "Closed cases with full window", "Of these, cases with follow-up", "Rate"], [
            [r["group"], r["closed_cases_with_full_window"], r["full_window_cases_with_followup"],
             "n/a" if r["full_window_followup_rate_pct"] is None else "{:.2f}%".format(r["full_window_followup_rate_pct"])]
            for r in result["by_category"]
        ]), "",
        "{:,.0f} closed cases lack a full observation window. No recorded follow-up is not proof that a customer had no further problem.".format(o["closed_cases_without_full_window"]), "",
        "## Individual histories", "",
    ]
    if account:
        history = [r for r in cases if r["account_id"] == account]
        if not history:
            raise ValueError("Account not found: " + account)
        selected = [{"account_id": account, "region_change_warning": len({r['region'] for r in history}) > 1,
                     "events": [public_case(r) for r in history],
                     "followup_pairs": [p for p in result['followup_pairs'] if p['account_id'] == account]}]
    else:
        def rank(h):
            score = max(({"metering_to_billing": 3, "estimated_read_to_disputed_bill": 3, "same_category": 2,
                          "different_category": 1}[p["relationship"]] for p in h["followup_pairs"]), default=0)
            return (-score, h["region_change_warning"], h["account_id"])
        selected = sorted(result["repeat_account_histories"], key=rank)[:examples]
    lines += ["Example accounts are selected by the stated relationship rules, not randomly. Their full recorded histories are shown, including conflicting regions. All repeated-account histories are in the JSON output.", ""]
    for h in selected:
        lines += ["### {}".format(h["account_id"]), ""]
        if h["region_change_warning"]:
            lines += ["**Region warning:** this account appears in multiple regions. Confirm the identity/property relationship before treating the full history as one continuing issue.", ""]
        lines += [md_table(["Complaint", "Opened", "Region", "Category", "Closed", "Recorded action", "Reopened flag"], [
            [e["complaint_id"], e["date_opened"], e["region"], e["category"], e["date_closed"] or "Open",
             e["resolution_action"] or "Not recorded", e["reopened"]] for e in h["events"]
        ]), ""]
        for p in h["followup_pairs"]:
            lines += ["- {} opened **{} days after** {} was marked closed, in the same region. Category sequence: **{} → {}**. This is a candidate connection, not a confirmed cause.".format(
                p["later_complaint_id"], p["days_after_closure"], p["first_complaint_id"], p["first_category"], p["later_category"])]
        if not h["followup_pairs"]:
            lines += ["No same-region post-closure pair met the selected window."]
        lines += [""]
    lines += [
        "## Interpretation and data quality", "",
        "- {:,} date-eligible pairs cross regions and are kept in `excluded_cross_region_pairs`, outside the main counts.".format(len(result["excluded_cross_region_pairs"])),
        "- Do not add reopened-case counts to new-follow-up counts: they describe different events and may overlap.",
        "- All earlier/later pairs are checked. One later complaint can match more than one earlier complaint; distinct-case and distinct-account counts prevent treating every pair as a separate customer.",
        "- 'Meter visit required' is not evidence of a completed visit; a correction value is not automatically a saving.",
        "- The data contains no complaint messages, verified cause IDs, property IDs or reopening dates. Rules flag histories to investigate.",
        "- This report uses only the complaint table. It does not claim a connection to individual meter readings or physical infrastructure.",
    ]
    return "\n".join(lines) + "\n"


def find_source():
    bases = list(dict.fromkeys([Path.cwd(), Path(__file__).resolve().parent.parent, Path(__file__).resolve().parent]))
    for base in bases:
        csv_path = base / "Northwind_Challenge_Data" / "northwind_complaints.csv"
        if csv_path.is_file():
            return csv_path, "csv"
    for base in bases:
        db_path = base / "data" / "data.db"
        if db_path.is_file():
            return db_path, "db"
    raise ValueError("No input found. Run from the repository or pass --csv PATH / --db PATH.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--csv", type=Path, help="Path to northwind_complaints.csv")
    inputs.add_argument("--db", type=Path, help="Read-only SQLite source with northwind_complaints table")
    parser.add_argument("--window-days", type=int, default=90, help="Maximum days after closure for a follow-up (default 90)")
    parser.add_argument("--snapshot-date", type=date.fromisoformat, help="Actual extract date YYYY-MM-DD; defaults to latest recorded event")
    parser.add_argument("--account", help="Show this account in the report; aggregate statistics still cover all input records")
    parser.add_argument("--examples", type=int, default=3, help="Number of example account timelines in the report (default 3)")
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent / "history_output")
    args = parser.parse_args(argv)
    if args.window_days < 1 or args.examples < 0:
        parser.error("--window-days must be positive and --examples must be non-negative")
    try:
        source, kind = (args.csv, "csv") if args.csv else (args.db, "db") if args.db else find_source()
        cases = load_cases(source, kind)
        result = analyse(cases, args.window_days, args.snapshot_date)
        result["metadata"]["source_file"] = Path(source).name
        result["metadata"]["source_sha256"] = hashlib.sha256(Path(source).read_bytes()).hexdigest()
        text = report(result, cases, args.examples, args.account)
        args.out_dir.mkdir(parents=True, exist_ok=True)
        markdown_path = args.out_dir / "complaint_history_report.md"
        json_path = args.out_dir / "complaint_history_data.json"
        markdown_path.write_text(text, encoding="utf-8")
        json_path.write_text(json.dumps(result, indent=2, default=str, allow_nan=False) + "\n", encoding="utf-8")
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, "Error: {}\n".format(exc))
    print(result["overview"]["story"])
    print("Report:", markdown_path)
    print("Dashboard data:", json_path)


if __name__ == "__main__":
    main()
