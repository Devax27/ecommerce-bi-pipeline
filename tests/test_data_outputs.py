"""Regression tests on the committed dashboard_data/*.csv files.

Expected values come from the verified SQL KPI results in docs/kpi_results.txt.
"""
from pathlib import Path

import pandas as pd
import pytest

from src import dashboard_metrics as dm

DATA_DIR = Path(__file__).resolve().parent.parent / "dashboard_data"


@pytest.fixture(scope="module")
def monthly_state():
    return pd.read_csv(DATA_DIR / "monthly_state.csv")


@pytest.fixture(scope="module")
def delivery():
    return pd.read_csv(DATA_DIR / "delivery_month_state.csv")


@pytest.fixture(scope="module")
def category():
    return pd.read_csv(DATA_DIR / "category_month.csv")


def test_months_are_the_20_complete_months(monthly_state):
    expected = list(pd.period_range("2017-01", "2018-08", freq="M").strftime("%Y-%m"))
    assert sorted(monthly_state["purchase_month"].unique()) == expected


def test_all_27_states_are_present(monthly_state):
    assert monthly_state["customer_state"].nunique() == 27
    assert monthly_state["customer_state"].str.len().eq(2).all()


def test_monthly_state_has_no_nulls_or_invalid_values(monthly_state):
    assert not monthly_state.isna().any().any()
    assert (monthly_state["orders"] > 0).all()
    assert (monthly_state[["revenue", "freight"]] >= 0).all().all()


def test_sales_totals_match_the_sql_kpis(monthly_state):
    s = dm.sales_summary(monthly_state)
    assert s["orders"] == 97_905
    assert s["revenue"] == pytest.approx(13_449_529.68, abs=0.5)
    assert s["freight"] == pytest.approx(2_234_177.06, abs=0.5)
    assert s["avg_order_value"] == pytest.approx(137.37, abs=0.01)


def test_delivery_totals_match_the_sql_kpis(delivery):
    d = dm.delivery_summary(delivery)
    assert d["delivered_orders"] == 96_203
    assert d["avg_delivery_days"] == pytest.approx(12.54, abs=0.006)
    assert d["late_rate_pct"] == pytest.approx(6.79, abs=0.006)
    assert d["avg_score_late"] == pytest.approx(2.27, abs=0.006)
    assert d["avg_score_on_time"] == pytest.approx(4.29, abs=0.006)


def test_delivery_rows_are_internally_consistent(delivery):
    assert (delivery["late_orders"] <= delivery["delivered_orders"]).all()
    assert (delivery["reviews"] <= delivery["delivered_orders"]).all()
    assert (delivery["late_reviews"] <= delivery["late_orders"]).all()
    # Every review score is between 1 and 5, so the sums are bounded by the counts.
    assert (delivery["review_score_sum"] >= delivery["reviews"]).all()
    assert (delivery["review_score_sum"] <= 5 * delivery["reviews"]).all()
    assert (delivery["late_review_sum"] >= delivery["late_reviews"]).all()
    assert (delivery["late_review_sum"] <= 5 * delivery["late_reviews"]).all()
    assert (delivery["total_delivery_days"] > 0).all()


def test_category_revenue_adds_up_to_monthly_revenue(category, monthly_state):
    by_month = category.groupby("purchase_month")["revenue"].sum()
    expected = monthly_state.groupby("purchase_month")["revenue"].sum()
    assert (by_month - expected).abs().max() < 0.01


def test_top_sellers_table():
    sellers = pd.read_csv(DATA_DIR / "top_sellers.csv")
    assert len(sellers) == 15
    assert sellers["revenue"].is_monotonic_decreasing
    assert sellers["seller_id"].str.len().eq(32).all()
    assert sellers["avg_review_score"].between(1, 5).all()


def test_seller_concentration_and_repeat_rate_match_the_sql_kpis():
    conc = pd.read_csv(DATA_DIR / "seller_concentration.csv").iloc[0]
    rep = pd.read_csv(DATA_DIR / "repeat_customers.csv").iloc[0]
    assert conc["active_sellers"] == 3029
    assert conc["top_decile_sellers_share_pct"] == pytest.approx(67.3)
    assert rep["customers"] == 94_707
    assert rep["repeat_rate_pct"] == pytest.approx(3.04)


def test_attribution_file_names_the_license():
    text = (DATA_DIR / "ATTRIBUTION.md").read_text(encoding="utf-8")
    assert "CC BY-NC-SA 4.0" in text
    assert "Olist" in text


def test_committed_dashboard_data_stays_small():
    total = sum(p.stat().st_size for p in DATA_DIR.iterdir())
    assert total < 1_000_000, "dashboard_data should only hold small aggregates, never raw data"