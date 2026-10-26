"""Pure functions that turn the aggregate tables in dashboard_data/ into dashboard metrics.

No Streamlit code lives here, so every function can be unit-tested.
"""
from __future__ import annotations

import pandas as pd


def safe_div(numerator: float, denominator: float) -> float | None:
    """Return numerator / denominator, or None when the denominator is zero."""
    if denominator == 0:
        return None
    return float(numerator) / float(denominator)


def filter_data(df: pd.DataFrame, start: str, end: str, states: list[str] | None = None) -> pd.DataFrame:
    """Keep rows whose purchase_month is in [start, end] (inclusive) and, optionally, whose state is selected.

    Months are 'YYYY-MM' strings, which sort correctly as text. states=None means no state filter;
    an empty list returns no rows. The state filter is ignored for tables without a customer_state column.
    """
    mask = (df["purchase_month"] >= start) & (df["purchase_month"] <= end)
    if states is not None and "customer_state" in df.columns:
        mask &= df["customer_state"].isin(states)
    return df[mask]


def sales_summary(df: pd.DataFrame) -> dict:
    orders = int(df["orders"].sum())
    revenue = float(df["revenue"].sum())
    freight = float(df["freight"].sum())
    return {
        "orders": orders,
        "revenue": revenue,
        "freight": freight,
        "avg_order_value": safe_div(revenue, orders),
    }


def monthly_sales(df: pd.DataFrame) -> pd.DataFrame:
    return df.groupby("purchase_month", as_index=False)[["orders", "revenue"]].sum()


def state_sales(df: pd.DataFrame) -> pd.DataFrame:
    out = df.groupby("customer_state", as_index=False)[["orders", "revenue"]].sum()
    out["avg_order_value"] = out["revenue"] / out["orders"]
    return out.sort_values("revenue", ascending=False).reset_index(drop=True)


def delivery_summary(df: pd.DataFrame) -> dict:
    delivered = int(df["delivered_orders"].sum())
    reviews = int(df["reviews"].sum())
    late_reviews = int(df["late_reviews"].sum())
    review_sum = float(df["review_score_sum"].sum())
    late_review_sum = float(df["late_review_sum"].sum())

    late_share = safe_div(df["late_orders"].sum(), delivered)
    return {
        "delivered_orders": delivered,
        "avg_delivery_days": safe_div(df["total_delivery_days"].sum(), delivered),
        "late_rate_pct": None if late_share is None else 100 * late_share,
        "avg_score_late": safe_div(late_review_sum, late_reviews),
        "avg_score_on_time": safe_div(review_sum - late_review_sum, reviews - late_reviews),
    }


def delivery_by_state(df: pd.DataFrame, min_orders: int = 100) -> pd.DataFrame:
    """Per-state delivery metrics, hiding states with fewer than min_orders delivered orders."""
    g = df.groupby("customer_state", as_index=False)[
        ["delivered_orders", "total_delivery_days", "late_orders"]
    ].sum()
    g = g[g["delivered_orders"] >= min_orders].copy()
    g["avg_delivery_days"] = g["total_delivery_days"] / g["delivered_orders"]
    g["late_rate_pct"] = 100 * g["late_orders"] / g["delivered_orders"]
    return g.sort_values("late_rate_pct", ascending=False).reset_index(drop=True)


def monthly_delivery(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("purchase_month", as_index=False)[
        ["delivered_orders", "total_delivery_days", "late_orders"]
    ].sum()
    g["avg_delivery_days"] = g["total_delivery_days"] / g["delivered_orders"]
    g["late_rate_pct"] = 100 * g["late_orders"] / g["delivered_orders"]
    return g


def category_summary(df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """Top categories by revenue. Review scores are averaged over item rows (see docs/kpi_definitions.md)."""
    g = df.groupby("category", as_index=False)[
        ["orders", "revenue", "review_item_rows", "review_score_sum"]
    ].sum()
    total = g["revenue"].sum()
    g["revenue_share_pct"] = (100 * g["revenue"] / total) if total else 0.0
    g["avg_review_score"] = g["review_score_sum"] / g["review_item_rows"].where(g["review_item_rows"] > 0)
    g = g.sort_values("revenue", ascending=False).head(top_n).reset_index(drop=True)
    return g[["category", "orders", "revenue", "revenue_share_pct", "avg_review_score"]]