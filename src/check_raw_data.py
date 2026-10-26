"""Quick sanity check: load every raw CSV and print its shape and columns."""
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def main() -> None:
    csv_files = sorted(RAW_DIR.glob("*.csv"))
    if not csv_files:
        raise SystemExit(f"No CSV files found in {RAW_DIR}")

    for path in csv_files:
        df = pd.read_csv(path)
        print(f"\n{path.name}: {df.shape[0]:,} rows x {df.shape[1]} columns")
        print("  columns:", ", ".join(df.columns))


if __name__ == "__main__":
    main()