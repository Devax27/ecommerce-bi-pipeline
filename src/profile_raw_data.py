"""Data-quality profile of the raw Olist CSVs.

Read-only: this script never modifies anything in data/raw.
Run from the project root:  python src\\profile_raw_data.py
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


def null_report(df: pd.DataFrame, name: str) -> None:
    nulls = df.isna().sum()
    nulls = nulls[nulls > 0]
    print(f"[{name}] columns with missing values:")
    if nulls.empty:
        print("  none")
        return
    for col, n in nulls.items():
        print(f"  {col}: {n:,} ({n / len(df):.1%})")


def duplicate_report(df: pd.DataFrame, name: str, key) -> None:
    full = int(df.duplicated().sum())
    by_key = int(df.duplicated(subset=key).sum())
    print(f"[{name}] fully duplicated rows: {full:,} | duplicate rows by key {key}: {by_key:,}")


def orphan_report(child, child_col, parent, parent_col, label: str) -> None:
    orphans = int((~child[child_col].isin(parent[parent_col])).sum())
    print(f"{label}: {orphans:,} orphan rows")


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

    section("1. MISSING VALUES")
    for name, df in [
        ("orders", orders), ("customers", customers), ("order_items", items),
        ("payments", payments), ("reviews", reviews), ("products", products),
        ("sellers", sellers), ("translation", translation), ("geolocation", geo),
    ]:
        null_report(df, name)

    section("2. DUPLICATES")
    duplicate_report(orders, "orders", "order_id")
    duplicate_report(customers, "customers", "customer_id")
    duplicate_report(items, "order_items", ["order_id", "order_item_id"])
    duplicate_report(payments, "payments", ["order_id", "payment_sequential"])
    duplicate_report(reviews, "reviews", "review_id")
    duplicate_report(products, "products", "product_id")
    duplicate_report(sellers, "sellers", "seller_id")
    duplicate_report(translation, "translation", "product_category_name")
    print(f"[geolocation] fully duplicated rows: {int(geo.duplicated().sum()):,}")
    print(f"[customers] unique people (customer_unique_id): {customers['customer_unique_id'].nunique():,}")

    section("3. REFERENTIAL INTEGRITY (orphan rows)")
    orphan_report(orders, "customer_id", customers, "customer_id", "orders -> customers")
    orphan_report(items, "order_id", orders, "order_id", "order_items -> orders")
    orphan_report(items, "product_id", products, "product_id", "order_items -> products")
    orphan_report(items, "seller_id", sellers, "seller_id", "order_items -> sellers")
    orphan_report(payments, "order_id", orders, "order_id", "payments -> orders")
    orphan_report(reviews, "order_id", orders, "order_id", "reviews -> orders")
    orphan_report(products.dropna(subset=["product_category_name"]), "product_category_name",
                  translation, "product_category_name", "products -> category translation")
    no_items = int((~orders["order_id"].isin(items["order_id"])).sum())
    print(f"orders with no order_items rows: {no_items:,}")

    section("4. ORDERS: STATUS AND DATES")
    print(orders["order_status"].value_counts().to_string())
    print(f"\npurchase date range: {orders['order_purchase_timestamp'].min()} "
          f"to {orders['order_purchase_timestamp'].max()}")
    print("\npurchases per month (first and last 3 months):")
    monthly = orders.groupby(orders["order_purchase_timestamp"].dt.to_period("M")).size()
    print(pd.concat([monthly.head(3), monthly.tail(3)]).to_string())
    delivered = orders["order_status"] == "delivered"
    print(f"\ndelivered orders missing a customer delivery date: "
          f"{int((delivered & orders['order_delivered_customer_date'].isna()).sum()):,}")
    print(f"non-delivered orders that have a customer delivery date: "
          f"{int((~delivered & orders['order_delivered_customer_date'].notna()).sum()):,}")
    print(f"delivered to customer BEFORE purchase: "
          f"{int((orders['order_delivered_customer_date'] < orders['order_purchase_timestamp']).sum()):,}")
    print(f"delivered to customer BEFORE carrier pickup: "
          f"{int((orders['order_delivered_customer_date'] < orders['order_delivered_carrier_date']).sum()):,}")

    section("5. VALUE SANITY")
    print(items[["price", "freight_value"]].describe().to_string())
    print(f"\nitems with price <= 0: {int((items['price'] <= 0).sum()):,}")
    print(f"items with negative freight: {int((items['freight_value'] < 0).sum()):,}")
    print("\npayment types:")
    print(payments["payment_type"].value_counts().to_string())
    print(f"\npayments with value <= 0: {int((payments['payment_value'] <= 0).sum()):,}")
    print("\nreview scores:")
    print(reviews["review_score"].value_counts().sort_index().to_string())
    print("\nproduct numeric columns:")
    print(products[["product_weight_g", "product_length_cm", "product_height_cm",
                    "product_width_cm"]].describe().to_string())
    print(f"\ncustomer states: {customers['customer_state'].nunique()}")


if __name__ == "__main__":
    main()