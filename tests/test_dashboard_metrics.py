"""Unit tests for src/dashboard_metrics.py (pure functions, no Streamlit needed)."""
import pandas as pd
import pytest

from src import dashboard_metrics as dm


@pytest.fixture
def sales():
    return pd.DataFrame({
        "purchase_month": ["2017-01", "2017-01", "2017-02", "2017-02"],
        "customer_state": ["SP", "RJ", "SP", "RJ"],
        "orders": [10, 5, 20, 5],
        "revenue": [1000.0, 600.0, 2000.0, 500.0],
        "freight": [100.0, 50.0, 200.0, 40.0],
    })


@pytest.fixture
def delivery():
    return pd.DataFrame({
        "purchase_month": ["2017-01", "2017-01", "2017-02"],
        "customer_state": ["SP", "AM", "SP"],
        "delivered_orders": [100, 50, 200],
        "total_delivery_days": [800.0, 1300.0, 1600.0],
        "late_orders": [5, 2, 20],
        "reviews": [90, 40, 180],
        "review_score_sum": [360, 120, 720],
        "late_reviews": [5, 2, 18],
        "late_review_sum": [10, 4, 36],
    })


@pytest.fixture
def category():
    return pd.DataFrame({
        "purchase_month": ["2017-01", "2017-02", "2017-01", "2017-02"],
        "category": ["toys", "toys", "auto", "auto"],
        "orders": [10, 20, 5, 5],
        "items": [12, 24, 6, 6],
        "revenue": [300.0, 700.0, 600.0, 600.0],
        "review_item_rows": [10, 20, 0, 0],
        "review_score_sum": [40, 80, 0, 0],
    })


# ------------------------------------------------------------------ safe_div
def test_safe_div_normal():
    assert dm.safe_div(10, 4) == 2.5


def test_safe_div_zero_denominator_returns_none():
    assert dm.safe_div(5, 0) is None


# --------------------------------------------------------------- filter_data
def test_filter_months_are_inclusive(sales):
    out = dm.filter_data(sales, "2017-02", "2017-02")
    assert len(out) == 2
    assert set(out["purchase_month"]) == {"2017-02"}


def test_filter_full_range_keeps_everything(sales):
    assert len(dm.filter_data(sales, "2017-01", "2017-02")) == 4


def test_filter_by_state(sales):
    out = dm.filter_data(sales, "2017-01", "2017-02", ["SP"])
    assert len(out) == 2
    assert set(out["customer_state"]) == {"SP"}


def test_filter_states_none_means_no_state_filter(sales):
    assert len(dm.filter_data(sales, "2017-01", "2017-02", None)) == 4


def test_filter_empty_state_list_returns_nothing(sales):
    assert len(dm.filter_data(sales, "2017-01", "2017-02", [])) == 0


def test_filter_months_outside_data_returns_nothing(sales):
    assert dm.filter_data(sales, "2019-01", "2019-12").empty


def test_filter_ignores_state_when_table_has_no_state_column(category):
    out = dm.filter_data(category, "2017-01", "2017-02", ["SP"])
    assert len(out) == 4


# ------------------------------------------------------------- sales metrics
def test_sales_summary(sales):
    s = dm.sales_summary(sales)
    assert s["orders"] == 40
    assert s["revenue"] == pytest.approx(4100.0)
    assert s["freight"] == pytest.approx(390.0)
    assert s["avg_order_value"] == pytest.approx(102.5)


def test_sales_summary_empty_has_no_average(sales):
    s = dm.sales_summary(sales.iloc[0:0])
    assert s["orders"] == 0
    assert s["revenue"] == 0.0
    assert s["avg_order_value"] is None


def test_monthly_sales_sums_states(sales):
    out = dm.monthly_sales(sales).set_index("purchase_month")
    assert out.loc["2017-01", "orders"] == 15
    assert out.loc["2017-01", "revenue"] == pytest.approx(1600.0)
    assert out.loc["2017-02", "orders"] == 25
    assert out.loc["2017-02", "revenue"] == pytest.approx(2500.0)


def test_state_sales_sorted_by_revenue_with_recomputed_average(sales):
    out = dm.state_sales(sales)
    assert out["customer_state"].tolist() == ["SP", "RJ"]
    assert out.loc[0, "avg_order_value"] == pytest.approx(100.0)  # 3000 / 30
    assert out.loc[1, "avg_order_value"] == pytest.approx(110.0)  # 1100 / 10


# ---------------------------------------------------------- delivery metrics
def test_delivery_summary(delivery):
    d = dm.delivery_summary(delivery)
    assert d["delivered_orders"] == 350
    assert d["avg_delivery_days"] == pytest.approx(3700 / 350)
    assert d["late_rate_pct"] == pytest.approx(100 * 27 / 350)
    assert d["avg_score_late"] == pytest.approx(2.0)                # 50 / 25
    assert d["avg_score_on_time"] == pytest.approx(1150 / 285)      # (1200-50) / (310-25)


def test_delivery_summary_empty_returns_none_not_zero_division(delivery):
    d = dm.delivery_summary(delivery.iloc[0:0])
    assert d["delivered_orders"] == 0
    assert d["avg_delivery_days"] is None
    assert d["late_rate_pct"] is None
    assert d["avg_score_late"] is None
    assert d["avg_score_on_time"] is None


def test_delivery_by_state_hides_small_states(delivery):
    out = dm.delivery_by_state(delivery, min_orders=100)
    assert out["customer_state"].tolist() == ["SP"]
    assert out.loc[0, "avg_delivery_days"] == pytest.approx(8.0)       # 2400 / 300
    assert out.loc[0, "late_rate_pct"] == pytest.approx(100 * 25 / 300)


def test_delivery_by_state_sorted_by_late_rate(delivery):
    out = dm.delivery_by_state(delivery, min_orders=50)
    assert out["customer_state"].tolist() == ["SP", "AM"]
    assert out.loc[1, "avg_delivery_days"] == pytest.approx(26.0)
    assert out.loc[1, "late_rate_pct"] == pytest.approx(4.0)


def test_monthly_delivery_recomputes_rates_from_sums(delivery):
    out = dm.monthly_delivery(delivery).set_index("purchase_month")
    assert out.loc["2017-01", "avg_delivery_days"] == pytest.approx(14.0)        # 2100 / 150
    assert out.loc["2017-01", "late_rate_pct"] == pytest.approx(100 * 7 / 150)
    assert out.loc["2017-02", "avg_delivery_days"] == pytest.approx(8.0)
    assert out.loc["2017-02", "late_rate_pct"] == pytest.approx(10.0)


# --------------------------------------------------------- category metrics
def test_category_summary_ranks_by_revenue(category):
    out = dm.category_summary(category, top_n=10)
    assert out["category"].tolist() == ["auto", "toys"]
    assert out.loc[0, "revenue"] == pytest.approx(1200.0)
    assert out["revenue_share_pct"].sum() == pytest.approx(100.0)
    assert out.loc[1, "revenue_share_pct"] == pytest.approx(100 * 1000 / 2200)


def test_category_summary_review_score_is_item_weighted_and_missing_when_no_reviews(category):
    out = dm.category_summary(category).set_index("category")
    assert out.loc["toys", "avg_review_score"] == pytest.approx(4.0)   # 120 / 30
    assert pd.isna(out.loc["auto", "avg_review_score"])


def test_category_summary_top_n(category):
    out = dm.category_summary(category, top_n=1)
    assert out["category"].tolist() == ["auto"]


def test_category_summary_empty_input(category):
    assert dm.category_summary(category.iloc[0:0]).empty