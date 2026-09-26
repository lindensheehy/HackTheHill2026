from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_DIR = REPO_ROOT / "Northwind_Challenge_Data"

def generate_csv_analysis(output_file=REPO_ROOT / "analysis" / "analysis_output.md"):
    # Find all CSV files in the data directory
    csv_files = sorted(CSV_DIR.glob("*.csv"))
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# CSV Frequency Analysis\n\n")
        
        if not csv_files:
            f.write("No `.csv` files were found in `Northwind_Challenge_Data/`.\n")
            print("No CSV files found.")
            return
            
        for file in csv_files:
            f.write(f"## File: `{file.name}`\n\n")
            
            try:
                # Read the CSV
                df = pd.read_csv(file)
                total_rows = len(df)
                f.write(f"**Total Rows:** {total_rows}\n\n")
                
                if total_rows == 0:
                    f.write("*This file is empty.*\n\n")
                    continue
                    
                # Iterate through each column
                for col in df.columns:
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
                    
            except Exception as e:
                f.write(f"> **Error processing `{file}`:** {str(e)}\n\n")
                print(f"Failed to process {file}: {e}")

    print(f"Success! Analysis written to {output_file}")

if __name__ == "__main__":
    generate_csv_analysis()