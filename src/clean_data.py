"""Clean the raw Olist CSVs and write analysis-ready Parquet files.

Raw files in data/raw are never modified. The rules are documented in
docs/cleaning_decisions.md.

Run from the project root:  python src\\clean_data.py
"""
import logging
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "processed"

ORDER_DATE_COLS = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]

# Complete months only: 2017-01-01 up to (not including) 2018-09-01.
ANALYSIS_START = pd.Timestamp("2017-01-01")
ANALYSIS_END = pd.Timestamp("2018-09-01")

NON_SALE_STATUSES = ["canceled", "unavailable"]

# Manual translations for categories missing from the dataset's translation file.
MANUAL_CATEGORY_TRANSLATIONS = {
    "portateis_cozinha_e_preparadores_de_alimentos": "portable_kitchen_and_food_preparers",
    "pc_gamer": "pc_gamer",
}

# Rough bounding box for Brazil (latitude, longitude).
BRAZIL_LAT = (-34.0, 6.0)
BRAZIL_LNG = (-74.0, -34.0)

# Row counts observed in the raw profile (docs/data_profile.txt).
EXPECTED_ROWS = {
    "orders": 99_441,
    "customers": 99_441,
    "order_items": 112_650,
    "payments": 103_886,
    "products": 32_951,
    "sellers": 3_095,
    "order_reviews": 98_673,
}

logger = logging.getLogger("clean_data")


def clean_orders(path: Path) -> pd.DataFrame:
    orders = pd.read_csv(path, parse_dates=ORDER_DATE_COLS)

    delivered = orders["order_status"] == "delivered"
    has_customer_date = orders["order_delivered_customer_date"].notna()
    orders["is_delivered_with_date"] = delivered & has_customer_date

    # Comparisons with missing dates evaluate to False, which is what we want.
    orders["has_date_inconsistency"] = (
        orders["order_delivered_customer_date"] < orders["order_delivered_carrier_date"]
    )

    delivery_days = (
        orders["order_delivered_customer_date"] - orders["order_purchase_timestamp"]
    ).dt.total_seconds() / 86400
    orders["delivery_days"] = delivery_days.where(orders["is_delivered_with_date"])

    # Positive = delivered after the estimated date (compared by calendar day).
    delay = (
        orders["order_delivered_customer_date"].dt.normalize()
        - orders["order_estimated_delivery_date"].dt.normalize()
    ).dt.days
    orders["delivery_delay_days"] = delay.where(orders["is_delivered_with_date"])

    purchase = orders["order_purchase_timestamp"]
    orders["purchase_month"] = purchase.dt.strftime("%Y-%m")
    orders["in_analysis_window"] = (purchase >= ANALYSIS_START) & (purchase < ANALYSIS_END)
    orders["counts_as_sale"] = ~orders["order_status"].isin(NON_SALE_STATUSES)
    return orders


def clean_customers(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def clean_items(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["shipping_limit_date"])


def clean_payments(path: Path) -> pd.DataFrame:
    payments = pd.read_csv(path)
    payments["is_zero_value"] = payments["payment_value"] <= 0
    return payments


def clean_reviews(path: Path) -> pd.DataFrame:
    """Return one review per order (the latest), plus how many reviews the order had."""
    reviews = pd.read_csv(path, parse_dates=["review_creation_date", "review_answer_timestamp"])
    reviews = reviews.sort_values(
        ["order_id", "review_creation_date", "review_answer_timestamp", "review_id"]
    )
    counts = reviews.groupby("order_id").size().rename("review_count")
    latest = reviews.drop_duplicates(subset="order_id", keep="last")
    latest = latest.set_index("order_id").join(counts).reset_index()
    latest["has_comment"] = latest["review_comment_message"].notna()
    return latest.drop(columns=["review_comment_title"])


def clean_products(products_path: Path, translation_path: Path) -> pd.DataFrame:
    products = pd.read_csv(products_path).rename(
        columns={
            "product_name_lenght": "product_name_length",
            "product_description_lenght": "product_description_length",
        }
    )
    translation = pd.read_csv(translation_path)
    mapping = dict(
        zip(translation["product_category_name"], translation["product_category_name_english"])
    )
    mapping.update(MANUAL_CATEGORY_TRANSLATIONS)
    products["product_category_name_english"] = (
        products["product_category_name"].map(mapping).fillna("unknown")
    )
    # A weight of 0 g is not physically valid.
    products["product_weight_g"] = products["product_weight_g"].mask(
        products["product_weight_g"] == 0
    )
    return products


def clean_sellers(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def build_zip_geolocation(path: Path) -> pd.DataFrame:
    """Collapse ~1M geolocation points to one median coordinate per zip prefix."""
    geo = pd.read_csv(path)
    in_box = geo["geolocation_lat"].between(*BRAZIL_LAT) & geo["geolocation_lng"].between(*BRAZIL_LNG)
    logger.info("geolocation: dropping %s points outside the Brazil bounding box", f"{int((~in_box).sum()):,}")
    geo = geo[in_box]
    return (
        geo.groupby("geolocation_zip_code_prefix")
        .agg(
            lat=("geolocation_lat", "median"),
            lng=("geolocation_lng", "median"),
            n_points=("geolocation_lat", "size"),
        )
        .reset_index()
        .rename(columns={"geolocation_zip_code_prefix": "zip_code_prefix"})
    )


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"Validation failed: {message}")
    logger.info("OK: %s", message)


def validate(t: dict) -> None:
    for name, expected in EXPECTED_ROWS.items():
        check(len(t[name]) == expected, f"{name} has {expected:,} rows")

    check(t["orders"]["order_id"].is_unique, "orders.order_id is unique")
    check(t["customers"]["customer_id"].is_unique, "customers.customer_id is unique")
    check(t["products"]["product_id"].is_unique, "products.product_id is unique")
    check(t["sellers"]["seller_id"].is_unique, "sellers.seller_id is unique")
    check(t["order_reviews"]["order_id"].is_unique, "order_reviews has one row per order")
    check(t["zip_geolocation"]["zip_code_prefix"].is_unique, "zip_geolocation has one row per prefix")

    check(t["orders"]["customer_id"].isin(t["customers"]["customer_id"]).all(), "orders -> customers")
    check(t["order_items"]["order_id"].isin(t["orders"]["order_id"]).all(), "order_items -> orders")
    check(t["order_items"]["product_id"].isin(t["products"]["product_id"]).all(), "order_items -> products")
    check(t["order_items"]["seller_id"].isin(t["sellers"]["seller_id"]).all(), "order_items -> sellers")
    check(t["payments"]["order_id"].isin(t["orders"]["order_id"]).all(), "payments -> orders")
    check(t["order_reviews"]["order_id"].isin(t["orders"]["order_id"]).all(), "order_reviews -> orders")

    check(t["products"]["product_category_name_english"].notna().all(), "every product has a category label")
    check((t["products"]["product_weight_g"].dropna() > 0).all(), "no product has weight <= 0")
    check((t["orders"]["delivery_days"].dropna() >= 0).all(), "no negative delivery_days")
    check((t["order_items"]["price"] > 0).all(), "all item prices are positive")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    tables = {
        "orders": clean_orders(RAW_DIR / "olist_orders_dataset.csv"),
        "customers": clean_customers(RAW_DIR / "olist_customers_dataset.csv"),
        "order_items": clean_items(RAW_DIR / "olist_order_items_dataset.csv"),
        "payments": clean_payments(RAW_DIR / "olist_order_payments_dataset.csv"),
        "order_reviews": clean_reviews(RAW_DIR / "olist_order_reviews_dataset.csv"),
        "products": clean_products(
            RAW_DIR / "olist_products_dataset.csv",
            RAW_DIR / "product_category_name_translation.csv",
        ),
        "sellers": clean_sellers(RAW_DIR / "olist_sellers_dataset.csv"),
        "zip_geolocation": build_zip_geolocation(RAW_DIR / "olist_geolocation_dataset.csv"),
    }

    o = tables["orders"]
    logger.info("delivered with date: %s", f"{int(o['is_delivered_with_date'].sum()):,}")
    logger.info("date inconsistencies: %s", f"{int(o['has_date_inconsistency'].sum()):,}")
    logger.info("in analysis window: %s", f"{int(o['in_analysis_window'].sum()):,}")
    logger.info("counted as sales: %s", f"{int(o['counts_as_sale'].sum()):,}")
    logger.info("products with unknown category: %s",
                f"{int((tables['products']['product_category_name_english'] == 'unknown').sum()):,}")
    logger.info("zip prefixes in lookup: %s", f"{len(tables['zip_geolocation']):,}")

    validate(tables)

    for name, df in tables.items():
        out_path = OUT_DIR / f"{name}.parquet"
        df.to_parquet(out_path, index=False)
        logger.info("wrote %s (%s rows, %s columns)", out_path.name, f"{len(df):,}", df.shape[1])


if __name__ == "__main__":
    main()