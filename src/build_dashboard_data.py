"""Build the aggregate tables that power the Streamlit dashboard.

Reads olist.db (read-only), validates every table against the SQL KPI results from
src/run_kpis.py, and writes small CSVs to dashboard_data/, which IS committed to Git.

Run from the project root:  python src\\build_dashboard_data.py
"""
import logging
import shutil
import sqlite3
from pathlib import Path

import pandas as pd

from run_kpis import parse_queries

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "processed" / "olist.db"
KPI_DIR = ROOT / "data" / "processed" / "kpis"
SQL_PATH = ROOT / "sql" / "dashboard_queries.sql"
OUT_DIR = ROOT / "dashboard_data"

KPI_INPUTS = [
    "monthly_kpis",
    "delivery_overall",
    "delivery_vs_reviews",
    "category_performance",
    "top_sellers",
    "seller_concentration",
    "repeat_customers",
]
# KPI tables that are small and static, copied as-is for the dashboard.
COPIED_KPIS = ["top_sellers", "seller_concentration", "repeat_customers"]

INT_SUM_COLUMNS = ["review_score_sum", "late_review_sum"]

ATTRIBUTION = """# Data attribution

These files are aggregates computed from the **Brazilian E-Commerce Public Dataset by Olist**
(https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce), licensed under CC BY-NC-SA 4.0
(https://creativecommons.org/licenses/by-nc-sa/4.0/).

They were changed from the original (orders, items, customers, products and reviews were cleaned,
filtered to 2017-01 to 2018-08 and summarized by month, state and category) and are shared under the
same license, for non-commercial portfolio use. Credit for the underlying data belongs to Olist.
"""

logger = logging.getLogger("build_dashboard_data")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"Validation failed: {message}")
    logger.info("OK: %s", message)


def within(a: float, b: float, tol: float) -> bool:
    return abs(float(a) - float(b)) <= tol


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Integer review sums (NULL -> 0) and exact-cent money columns."""
    for col in INT_SUM_COLUMNS:
        if col in df.columns:
            df[col] = df[col].fillna(0).astype(int)
    # Prices have two decimals, so rounding each cell recovers exact cents.
    return df.round({"revenue": 2, "freight": 2, "total_delivery_days": 4})


def validate(t: dict, kpi: dict) -> None:
    # --- monthly_state vs monthly_kpis -------------------------------------------------
    by_month = t["monthly_state"].groupby("purchase_month")[["orders", "revenue", "freight"]].sum()
    k = kpi["monthly_kpis"].set_index("purchase_month")
    check(list(by_month.index) == list(k.index), f"monthly_state covers the same {len(k)} months as the SQL KPIs")
    check((by_month["orders"] == k["orders"]).all(), "monthly_state orders match the SQL KPIs for every month")
    check((by_month["revenue"] - k["revenue"]).abs().max() < 0.01, "monthly_state revenue matches the SQL KPIs for every month")
    check((by_month["freight"] - k["freight"]).abs().max() < 0.01, "monthly_state freight matches the SQL KPIs for every month")

    # --- delivery_month_state vs delivery_overall and delivery_vs_reviews --------------
    dl = t["delivery_month_state"]
    kd = kpi["delivery_overall"].iloc[0]
    delivered = int(dl["delivered_orders"].sum())
    check(delivered == int(kd["delivered_orders"]), f"delivered orders match the SQL KPI ({delivered:,})")
    check(within(dl["total_delivery_days"].sum() / delivered, kd["avg_delivery_days"], 0.005 + 1e-9),
          "average delivery days match the SQL KPI")
    check(within(100 * dl["late_orders"].sum() / delivered, kd["late_rate_pct"], 0.005 + 1e-9),
          "late delivery rate matches the SQL KPI")

    kvr = kpi["delivery_vs_reviews"].set_index("delivery_outcome")
    late_n = int(dl["late_reviews"].sum())
    late_sum = int(dl["late_review_sum"].sum())
    all_n = int(dl["reviews"].sum())
    all_sum = int(dl["review_score_sum"].sum())
    check(late_n == int(kvr.loc["late", "orders"]), "reviewed late orders match the SQL KPI")
    check(all_n - late_n == int(kvr.loc["on_time_or_early", "orders"]), "reviewed on-time orders match the SQL KPI")
    check(within(late_sum / late_n, kvr.loc["late", "avg_review_score"], 0.005 + 1e-9), "late review score matches the SQL KPI")
    check(within((all_sum - late_sum) / (all_n - late_n), kvr.loc["on_time_or_early", "avg_review_score"], 0.005 + 1e-9),
          "on-time review score matches the SQL KPI")

    # --- category_month vs monthly_kpis and category_performance -----------------------
    cm = t["category_month"]
    cat_by_month = cm.groupby("purchase_month")["revenue"].sum()
    check((cat_by_month - k["revenue"]).abs().max() < 0.01, "category_month revenue sums to the monthly revenue")

    agg = cm.groupby("category").agg(
        orders=("orders", "sum"),
        revenue=("revenue", "sum"),
        score_sum=("review_score_sum", "sum"),
        score_n=("review_item_rows", "sum"),
    )
    kc = kpi["category_performance"].set_index("category")
    sub = agg.loc[kc.index]
    check((sub["orders"] == kc["orders"]).all(), "top-15 category order counts match the SQL KPI")
    check((sub["revenue"] - kc["revenue"]).abs().max() < 0.01, "top-15 category revenue matches the SQL KPI")
    check(((sub["score_sum"] / sub["score_n"]) - kc["avg_review_score"]).abs().max() <= 0.005 + 1e-9,
          "top-15 category review scores match the SQL KPI")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    missing = [n for n in KPI_INPUTS if not (KPI_DIR / f"{n}.csv").exists()]
    if missing:
        raise SystemExit(f"Missing KPI files {missing}. Run: python src\\run_kpis.py")

    queries = parse_queries(SQL_PATH.read_text(encoding="utf-8"))

    conn = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
    try:
        tables = {name: normalize(pd.read_sql_query(sql, conn)) for name, sql in queries.items()}
    finally:
        conn.close()

    kpi = {name: pd.read_csv(KPI_DIR / f"{name}.csv") for name in KPI_INPUTS}
    validate(tables, kpi)

    OUT_DIR.mkdir(exist_ok=True)
    for name, df in tables.items():
        path = OUT_DIR / f"{name}.csv"
        df.to_csv(path, index=False)
        logger.info("wrote %s (%s rows, %.1f KB)", path.name, f"{len(df):,}", path.stat().st_size / 1024)
    for name in COPIED_KPIS:
        shutil.copy(KPI_DIR / f"{name}.csv", OUT_DIR / f"{name}.csv")
        logger.info("copied %s.csv", name)
    (OUT_DIR / "ATTRIBUTION.md").write_text(ATTRIBUTION, encoding="utf-8")
    logger.info("dashboard data ready in %s", OUT_DIR)


if __name__ == "__main__":
    main()