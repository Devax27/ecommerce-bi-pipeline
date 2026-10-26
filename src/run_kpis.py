"""Run every query in sql/kpi_queries.sql, save CSVs, and cross-check the monthly KPIs with pandas.

Run from the project root:  python src\\run_kpis.py
"""
import logging
import re
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
DB_PATH = PROCESSED_DIR / "olist.db"
SQL_PATH = ROOT / "sql" / "kpi_queries.sql"
OUT_DIR = PROCESSED_DIR / "kpis"

logger = logging.getLogger("run_kpis")


def parse_queries(text: str) -> dict:
    """Split the SQL file into {name: sql} using '-- name: <identifier>' marker lines."""
    queries, name, lines = {}, None, []
    for line in text.splitlines():
        match = re.match(r"^--\s*name:\s*(\w+)\s*$", line)
        if match:
            if name:
                queries[name] = "\n".join(lines).strip()
            name, lines = match.group(1), []
        elif name:
            lines.append(line)
    if name:
        queries[name] = "\n".join(lines).strip()
    if not queries:
        raise ValueError(f"No '-- name:' markers found in {SQL_PATH}")
    return queries


def cross_check_monthly(sql_monthly: pd.DataFrame) -> None:
    """Recompute monthly orders and revenue from the Parquet files and compare with the SQL result."""
    orders = pd.read_parquet(PROCESSED_DIR / "orders.parquet")
    items = pd.read_parquet(PROCESSED_DIR / "order_items.parquet")
    window = orders[orders["in_analysis_window"] & orders["counts_as_sale"]]
    merged = window[["order_id", "purchase_month"]].merge(items[["order_id", "price"]], on="order_id")
    expected = merged.groupby("purchase_month").agg(
        orders=("order_id", "nunique"), revenue=("price", "sum")
    )

    expected = expected.rename(columns={"orders": "orders_pd", "revenue": "revenue_pd"})
    compared = sql_monthly.set_index("purchase_month")[["orders", "revenue"]].join(
        expected, how="outer"
    )
    if compared.isna().any().any():
        raise ValueError("Cross-check failed: the SQL and pandas results cover different months")
    if not (compared["orders"] == compared["orders_pd"]).all():
        raise ValueError("Cross-check failed: monthly order counts differ")
    if not ((compared["revenue"] - compared["revenue_pd"]).abs() < 0.01).all():
        raise ValueError("Cross-check failed: monthly revenue differs by more than 0.01")
    logger.info("OK: monthly orders and revenue match an independent pandas calculation (%d months)", len(compared))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logger.info("SQLite version: %s", sqlite3.sqlite_version)

    queries = parse_queries(SQL_PATH.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Open read-only so the KPI queries can never modify the database.
    conn = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
    results = {}
    try:
        for name, sql in queries.items():
            df = pd.read_sql_query(sql, conn)
            results[name] = df
            df.to_csv(OUT_DIR / f"{name}.csv", index=False)
            print(f"\n--- {name} ({len(df)} rows) ---")
            print(df.to_string(index=False))
    finally:
        conn.close()

    print()
    cross_check_monthly(results["monthly_kpis"])
    logger.info("wrote %d CSV files to %s", len(results), OUT_DIR)


if __name__ == "__main__":
    main()