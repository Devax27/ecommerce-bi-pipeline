"""Tests for the cleaning rules in src/clean_data.py, using tiny synthetic CSVs (no real data needed)."""
import pandas as pd
import pytest

from src import clean_data

ORDER_COLS = [
    "order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_approved_at",
    "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date",
]


def o(order_id, status, purchase, approved, carrier, delivered, estimated):
    return (order_id, "c1", status, purchase, approved, carrier, delivered, estimated)


@pytest.fixture
def orders_clean(tmp_path):
    rows = [
        o("on_time", "delivered", "2017-03-01 10:00:00", "2017-03-01 11:00:00",
          "2017-03-02 09:00:00", "2017-03-11 10:00:00", "2017-03-15 00:00:00"),
        o("late", "delivered", "2017-04-01 08:00:00", "2017-04-01 09:00:00",
          "2017-04-02 09:00:00", "2017-04-20 09:00:00", "2017-04-10 00:00:00"),
        o("canceled", "canceled", "2017-05-01 12:00:00", None, None, None, "2017-05-20 00:00:00"),
        o("before_window", "delivered", "2016-12-20 12:00:00", "2016-12-20 13:00:00",
          "2016-12-21 09:00:00", "2016-12-30 10:00:00", "2017-01-10 00:00:00"),
        o("last_second", "processing", "2018-08-31 23:59:59", "2018-09-01 08:00:00",
          None, None, "2018-09-20 00:00:00"),
        o("first_after", "processing", "2018-09-01 00:00:00", "2018-09-01 08:00:00",
          None, None, "2018-09-20 00:00:00"),
        o("inconsistent", "delivered", "2017-06-01 10:00:00", "2017-06-01 11:00:00",
          "2017-06-10 09:00:00", "2017-06-08 10:00:00", "2017-06-20 00:00:00"),
        o("no_date", "delivered", "2017-07-01 10:00:00", "2017-07-01 11:00:00",
          "2017-07-02 09:00:00", None, "2017-07-20 00:00:00"),
    ]
    path = tmp_path / "orders.csv"
    pd.DataFrame(rows, columns=ORDER_COLS).to_csv(path, index=False)
    return clean_data.clean_orders(path).set_index("order_id")


# -------------------------------------------------------------------- orders
def test_on_time_delivery_metrics(orders_clean):
    row = orders_clean.loc["on_time"]
    assert bool(row["is_delivered_with_date"]) is True
    assert row["delivery_days"] == pytest.approx(10.0)
    assert row["delivery_delay_days"] == -4          # delivered 4 calendar days early
    assert bool(row["has_date_inconsistency"]) is False
    assert row["purchase_month"] == "2017-03"


def test_late_delivery_metrics(orders_clean):
    row = orders_clean.loc["late"]
    assert row["delivery_days"] == pytest.approx(19 + 1 / 24)
    assert row["delivery_delay_days"] == 10


def test_canceled_order_is_not_a_sale_and_has_no_delivery_metrics(orders_clean):
    row = orders_clean.loc["canceled"]
    assert bool(row["counts_as_sale"]) is False
    assert bool(row["is_delivered_with_date"]) is False
    assert pd.isna(row["delivery_days"])
    assert pd.isna(row["delivery_delay_days"])


def test_delivered_status_without_delivery_date_is_excluded_from_delivery_metrics(orders_clean):
    row = orders_clean.loc["no_date"]
    assert bool(row["is_delivered_with_date"]) is False
    assert pd.isna(row["delivery_days"])
    assert bool(row["has_date_inconsistency"]) is False


def test_delivery_before_carrier_pickup_is_flagged_but_kept(orders_clean):
    row = orders_clean.loc["inconsistent"]
    assert bool(row["has_date_inconsistency"]) is True
    assert bool(row["is_delivered_with_date"]) is True
    assert row["delivery_days"] == pytest.approx(7.0)


def test_analysis_window_boundaries(orders_clean):
    assert bool(orders_clean.loc["before_window", "in_analysis_window"]) is False
    assert bool(orders_clean.loc["on_time", "in_analysis_window"]) is True
    assert bool(orders_clean.loc["last_second", "in_analysis_window"]) is True    # 2018-08-31 23:59:59
    assert bool(orders_clean.loc["first_after", "in_analysis_window"]) is False   # 2018-09-01 00:00:00


def test_no_delivery_days_are_negative(orders_clean):
    assert (orders_clean["delivery_days"].dropna() >= 0).all()


# ------------------------------------------------------------------- reviews
def test_reviews_keep_latest_per_order_and_count_them(tmp_path):
    cols = ["review_id", "order_id", "review_score", "review_comment_title", "review_comment_message",
            "review_creation_date", "review_answer_timestamp"]
    rows = [
        ("r1", "A", 1, None, "bad", "2018-01-01 00:00:00", "2018-01-02 10:00:00"),
        ("r2", "A", 5, None, "fixed", "2018-01-05 00:00:00", "2018-01-06 10:00:00"),
        ("r3", "B", 4, "ok", None, "2018-02-01 00:00:00", "2018-02-02 10:00:00"),
        ("r1", "C", 1, None, None, "2018-01-01 00:00:00", "2018-01-02 10:00:00"),  # review_id reused on another order
    ]
    path = tmp_path / "reviews.csv"
    pd.DataFrame(rows, columns=cols).to_csv(path, index=False)

    out = clean_data.clean_reviews(path).set_index("order_id")
    assert len(out) == 3
    assert out.index.is_unique
    assert out.loc["A", "review_id"] == "r2"
    assert out.loc["A", "review_score"] == 5
    assert out.loc["A", "review_count"] == 2
    assert out.loc["B", "review_count"] == 1
    assert bool(out.loc["A", "has_comment"]) is True
    assert bool(out.loc["B", "has_comment"]) is False
    assert "review_comment_title" not in out.columns


# ------------------------------------------------------------------ products
def test_products_translation_unknown_and_weight_rules(tmp_path):
    cols = ["product_id", "product_category_name", "product_name_lenght", "product_description_lenght",
            "product_photos_qty", "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"]
    rows = [
        ("p1", "cat_a", 20, 100, 2, 500.0, 10, 10, 10),
        ("p2", None, None, None, None, 300.0, 10, 10, 10),
        ("p3", "pc_gamer", 20, 100, 2, 1000.0, 10, 10, 10),
        ("p4", "portateis_cozinha_e_preparadores_de_alimentos", 20, 100, 2, 0.0, 10, 10, 10),
    ]
    products_path = tmp_path / "products.csv"
    translation_path = tmp_path / "translation.csv"
    pd.DataFrame(rows, columns=cols).to_csv(products_path, index=False)
    pd.DataFrame({"product_category_name": ["cat_a"],
                  "product_category_name_english": ["category_a"]}).to_csv(translation_path, index=False)

    out = clean_data.clean_products(products_path, translation_path).set_index("product_id")
    assert out.loc["p1", "product_category_name_english"] == "category_a"
    assert out.loc["p2", "product_category_name_english"] == "unknown"
    assert out.loc["p3", "product_category_name_english"] == "pc_gamer"
    assert out.loc["p4", "product_category_name_english"] == "portable_kitchen_and_food_preparers"
    assert pd.isna(out.loc["p4", "product_weight_g"])          # a weight of 0 g is invalid
    assert out.loc["p1", "product_weight_g"] == 500.0
    assert "product_name_length" in out.columns
    assert "product_description_length" in out.columns
    assert "product_name_lenght" not in out.columns


# --------------------------------------------------------------- geolocation
def test_geolocation_uses_median_and_drops_points_outside_brazil(tmp_path):
    cols = ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng",
            "geolocation_city", "geolocation_state"]
    rows = [
        (1000, -23.5, -46.6, "x", "SP"),
        (1000, -23.6, -46.7, "x", "SP"),
        (1000, -23.7, -46.5, "x", "SP"),
        (2000, 40.0, 10.0, "x", "XX"),      # only point is outside the Brazil box -> prefix disappears
        (3000, -10.0, -50.0, "x", "MT"),
        (3000, 40.0, 10.0, "x", "XX"),      # outside point dropped, inside point kept
    ]
    path = tmp_path / "geo.csv"
    pd.DataFrame(rows, columns=cols).to_csv(path, index=False)

    out = clean_data.build_zip_geolocation(path).set_index("zip_code_prefix")
    assert set(out.index) == {1000, 3000}
    assert out.loc[1000, "lat"] == pytest.approx(-23.6)
    assert out.loc[1000, "lng"] == pytest.approx(-46.6)
    assert out.loc[1000, "n_points"] == 3
    assert out.loc[3000, "n_points"] == 1


# ---------------------------------------------------------------- validation
def test_check_raises_when_condition_is_false():
    with pytest.raises(ValueError, match="Validation failed"):
        clean_data.check(False, "something is wrong")


def test_check_passes_silently_when_condition_is_true():
    clean_data.check(True, "everything is fine")