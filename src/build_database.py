"""Build the SQLite database from data/processed/*.parquet and verify the load.

Run from the project root:  python src\\build_database.py
"""
import logging
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
SCHEMA_PATH = ROOT / "sql" / "schema.sql"
DB_PATH = PROCESSED_DIR / "olist.db"

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Parents first, so foreign keys are satisfied while loading.
LOAD_ORDER = [
    "customers",
    "sellers",
    "products",
    "orders",
    "order_items",
    "payments",
    "order_reviews",
    "zip_geolocation",
]

# NULL counts known from the raw profile (docs/data_profile.txt) and cleaning rules.
EXPECTED_NULLS = [
    ("orders", "order_approved_at", 160),
    ("orders", "order_delivered_carrier_date", 1_783),
    ("orders", "order_delivered_customer_date", 2_965),
    ("products", "product_category_name", 610),
    ("products", "product_weight_g", 6),  # 2 missing in raw + 4 zero weights set to missing
]

logger = logging.getLogger("build_database")


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Convert a DataFrame into values SQLite stores cleanly (text dates, 0/1 booleans, real NULLs)."""
    df = df.copy()
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime(DATE_FORMAT)
        elif pd.api.types.is_bool_dtype(df[col]):
            df[col] = df[col].astype(int)
    df = df.astype(object)
    return df.where(df.notna(), None)


def scalar(conn: sqlite3.Connection, sql: str):
    return conn.execute(sql).fetchone()[0]


def verify(conn: sqlite3.Connection, tables: dict) -> None:
    for name, df in tables.items():
        n = scalar(conn, f"SELECT COUNT(*) FROM {name}")
        if n != len(df):
            raise ValueError(f"Row count mismatch in {name}: database {n:,} vs parquet {len(df):,}")
        logger.info("OK: %s has %s rows", name, f"{n:,}")

    result = scalar(conn, "PRAGMA integrity_check")
    if result != "ok":
        raise ValueError(f"integrity_check failed: {result}")
    logger.info("OK: integrity_check")

    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise ValueError(f"foreign_key_check found {len(violations)} violations, e.g. {violations[:3]}")
    logger.info("OK: foreign_key_check found no violations")

    for table, column, expected in EXPECTED_NULLS:
        n = scalar(conn, f"SELECT COUNT(*) FROM {table} WHERE {column} IS NULL")
        if n != expected:
            raise ValueError(f"{table}.{column}: {n:,} NULLs, expected {expected:,}")
        logger.info("OK: %s.%s has %s NULLs", table, column, f"{n:,}")

    # Cross-check one business number between pandas and SQL.
    items = tables["order_items"].merge(
        tables["orders"][["order_id", "counts_as_sale"]], on="order_id"
    )
    pandas_revenue = round(float(items.loc[items["counts_as_sale"], "price"].sum()), 2)
    sql_revenue = scalar(
        conn,
        "SELECT ROUND(SUM(oi.price), 2) FROM order_items oi "
        "JOIN orders o ON o.order_id = oi.order_id WHERE o.counts_as_sale = 1",
    )
    if abs(pandas_revenue - sql_revenue) > 0.01:
        raise ValueError(f"Revenue mismatch: pandas {pandas_revenue:,.2f} vs SQL {sql_revenue:,.2f}")
    logger.info("OK: revenue (items price, counted sales) matches: %s", f"{sql_revenue:,.2f}")

    first, last = conn.execute(
        "SELECT MIN(order_purchase_timestamp), MAX(order_purchase_timestamp) FROM orders"
    ).fetchone()
    logger.info("purchase timestamps stored as text: %s to %s", first, last)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    tables = {name: pd.read_parquet(PROCESSED_DIR / f"{name}.parquet") for name in LOAD_ORDER}

    if DB_PATH.exists():
        DB_PATH.unlink()
        logger.info("removed old database")

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        for name in LOAD_ORDER:
            prepare(tables[name]).to_sql(name, conn, if_exists="append", index=False, chunksize=10_000)
            logger.info("loaded %s (%s rows)", name, f"{len(tables[name]):,}")
        conn.commit()
        verify(conn, tables)
    finally:
        conn.close()

    logger.info("database ready: %s (%.1f MB)", DB_PATH, DB_PATH.stat().st_size / 1_048_576)


if __name__ == "__main__":
    main()