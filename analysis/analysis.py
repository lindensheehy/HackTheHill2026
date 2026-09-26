import sqlite3
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "data.db"
TABLE = "northwind_complaints"

# Identifiers, dates and continuous values have too many distinct values for frequency counts to be useful
EXCLUDED_COLUMNS = {
    "complaint_id",
    "account_id",
    "date_opened",
    "date_closed",
    "days_to_close",
    "bill_correction_value",
}

def generate_frequency_analysis(output_file=REPO_ROOT / "analysis" / "analysis_output.md"):
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql(f"SELECT * FROM {TABLE}", conn)
    total_rows = len(df)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# Complaints Frequency Analysis\n\n")
        f.write(f"## Table: `{TABLE}`\n\n")
        f.write(f"**Total Rows:** {total_rows}\n\n")

        if total_rows == 0:
            f.write("*This table is empty.*\n")
            print(f"{TABLE} is empty.")
            return

        # Iterate through each categorical column
        for col in df.columns:
            if col in EXCLUDED_COLUMNS:
                continue

            f.write(f"### {col}\n\n")

            # Calculate frequency counts, including missing values (NaN)
            counts = df[col].value_counts(dropna=False)

            # Write out each value's count and percentage
            for val, count in counts.items():
                # Calculate percentage based on total rows
                pct = (count / total_rows) * 100

                # Handle missing/NaN values gracefully for the report
                val_str = "*(Blank / Missing)*" if pd.isna(val) else str(val)

                f.write(f"- **{val_str}**: {count} ({pct:.1f}%)\n")

            f.write("\n") # Add a blank line between columns

    print(f"Success! Analysis written to {output_file}")

if __name__ == "__main__":
    generate_frequency_analysis()
