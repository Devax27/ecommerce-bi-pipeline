"""Targeted, read-only investigation of anomalies found by profile_raw_data.py.

Run from the project root:  python src\\investigate_anomalies.py
"""
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

ORDER_DATE_COLS = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def main() -> None:
    orders = pd.read_csv(RAW_DIR / "olist_orders_dataset.csv", parse_dates=ORDER_DATE_COLS)
    customers = pd.read_csv(RAW_DIR / "olist_customers_dataset.csv")
    items = pd.read_csv(RAW_DIR / "olist_order_items_dataset.csv")
    payments = pd.read_csv(RAW_DIR / "olist_order_payments_dataset.csv")
    reviews = pd.read_csv(RAW_DIR / "olist_order_reviews_dataset.csv")
    products = pd.read_csv(RAW_DIR / "olist_products_dataset.csv")
    sellers = pd.read_csv(RAW_DIR / "olist_sellers_dataset.csv")
    translation = pd.read_csv(RAW_DIR / "product_category_name_translation.csv")
    geo = pd.read_csv(RAW_DIR / "olist_geolocation_dataset.csv")

    section("A. REVIEWS: duplicate review_id")
    dup_mask = reviews["review_id"].duplicated(keep=False)
    dups = reviews[dup_mask].sort_values(["review_id", "order_id"])
    print(f"distinct review_ids appearing more than once: {dups['review_id'].nunique():,}")
    print(f"rows involved: {len(dups):,}")
    orders_per_id = dups.groupby("review_id")["order_id"].nunique()
    print(f"review_ids linked to more than one distinct order_id: {int((orders_per_id > 1).sum()):,}")
    print(f"duplicated (review_id, order_id) pairs: "
          f"{int(reviews.duplicated(subset=['review_id', 'order_id']).sum()):,}")
    print("\nnumber of review rows per order (value = how many orders):")
    print(reviews.groupby("order_id").size().value_counts().sort_index().to_string())
    print("\nsample duplicated review_id rows:")
    print(dups[["review_id", "order_id", "review_score", "review_creation_date"]]
          .head(6).to_string(index=False))

    section("B. ORDERS WITH NO ITEM ROWS: status")
    no_items = orders[~orders["order_id"].isin(items["order_id"])]
    print(no_items["order_status"].value_counts().to_string())

    section("C. ORDER DATE ANOMALIES")
    delivered = orders["order_status"] == "delivered"
    a = orders[delivered & orders["order_delivered_customer_date"].isna()]
    print(f"delivered but missing customer delivery date: {len(a)}")
    print(a[["order_id", "order_purchase_timestamp", "order_delivered_carrier_date",
             "order_estimated_delivery_date"]].to_string(index=False))
    b = orders[~delivered & orders["order_delivered_customer_date"].notna()]
    print(f"\nnon-delivered orders WITH a customer delivery date: {len(b)}")
    print(b["order_status"].value_counts().to_string())
    c = orders[orders["order_delivered_customer_date"] < orders["order_delivered_carrier_date"]]
    gap_days = (c["order_delivered_carrier_date"] - c["order_delivered_customer_date"]).dt.total_seconds() / 86400
    print(f"\ndelivered BEFORE carrier pickup: {len(c)} orders; gap in days:")
    print(gap_days.describe().to_string())

    section("D. PAYMENTS: zero or negative, not_defined")
    print(payments[payments["payment_value"] <= 0].to_string(index=False))
    print("\nrows with payment_type == not_defined:")
    print(payments[payments["payment_type"] == "not_defined"].to_string(index=False))

    section("E. REVENUE RECONCILIATION: payments vs items")
    item_totals = items.groupby("order_id").agg(
        items_price=("price", "sum"), items_freight=("freight_value", "sum")
    )
    item_totals["items_total"] = item_totals["items_price"] + item_totals["items_freight"]
    pay_totals = payments.groupby("order_id")["payment_value"].sum().rename("payments_total")
    both = item_totals.join(pay_totals, how="inner")
    diff = (both["payments_total"] - both["items_total"]).abs()
    print(f"orders with both items and payments: {len(both):,}")
    print(f"payments total differs from items price+freight by > 0.01: {int((diff > 0.01).sum()):,}")
    print(f"payments total differs from items price+freight by > 1.00: {int((diff > 1.00).sum()):,}")
    print(f"sum of payments: {both['payments_total'].sum():,.2f}")
    print(f"sum of items price + freight: {both['items_total'].sum():,.2f}")
    print(f"sum of items price only: {both['items_price'].sum():,.2f}")

    section("F. PRODUCTS")
    unmatched = products[
        products["product_category_name"].notna()
        & ~products["product_category_name"].isin(translation["product_category_name"])
    ]
    print("categories with no English translation (rows per category):")
    print(unmatched["product_category_name"].value_counts().to_string())
    print(f"\nproducts with weight == 0: {int((products['product_weight_g'] == 0).sum()):,}")
    no_cat_ids = products.loc[products["product_category_name"].isna(), "product_id"]
    print(f"order_items rows whose product has no category: {int(items['product_id'].isin(no_cat_ids).sum()):,} "
          f"of {len(items):,}")

    section("G. ORDERS PER MONTH (all months)")
    monthly = orders.groupby(orders["order_purchase_timestamp"].dt.to_period("M")).size()
    print(monthly.to_string())

    section("H. GEOLOCATION")
    print(f"distinct zip prefixes in geolocation: {geo['geolocation_zip_code_prefix'].nunique():,}")
    per_prefix = geo.groupby("geolocation_zip_code_prefix")[["geolocation_lat", "geolocation_lng"]].nunique()
    print(f"prefixes with more than one distinct latitude: {int((per_prefix['geolocation_lat'] > 1).sum()):,}")
    outside = geo[
        ~geo["geolocation_lat"].between(-34, 6) | ~geo["geolocation_lng"].between(-74, -34)
    ]
    print(f"rows outside a rough Brazil bounding box: {len(outside):,}")
    known = set(geo["geolocation_zip_code_prefix"])
    print(f"customer zip prefixes missing from geolocation: "
          f"{int((~customers['customer_zip_code_prefix'].isin(known)).sum()):,} of {len(customers):,} customers")
    print(f"seller zip prefixes missing from geolocation: "
          f"{int((~sellers['seller_zip_code_prefix'].isin(known)).sum()):,} of {len(sellers):,} sellers")


if __name__ == "__main__":
    main()