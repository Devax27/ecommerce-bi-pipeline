"""Tests for sql/schema.sql constraints and for the syntax of every SQL query we ship."""
import sqlite3
from pathlib import Path

import pytest

from src.run_kpis import parse_queries

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "sql" / "schema.sql"
KPI_QUERIES = parse_queries((ROOT / "sql" / "kpi_queries.sql").read_text(encoding="utf-8"))
DASHBOARD_QUERIES = parse_queries((ROOT / "sql" / "dashboard_queries.sql").read_text(encoding="utf-8"))


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    c.executescript(SCHEMA.read_text(encoding="utf-8"))
    yield c
    c.close()


def seed(conn):
    conn.execute("INSERT INTO customers VALUES ('c1', 'u1', 1000, 'sao paulo', 'SP')")
    conn.execute("INSERT INTO sellers VALUES ('s1', 1000, 'sao paulo', 'SP')")
    conn.execute("INSERT INTO products (product_id, product_category_name_english) VALUES ('p1', 'toys')")
    conn.execute(
        "INSERT INTO orders (order_id, customer_id, order_status, order_purchase_timestamp, "
        "order_estimated_delivery_date, is_delivered_with_date, has_date_inconsistency, "
        "purchase_month, in_analysis_window, counts_as_sale) "
        "VALUES ('o1', 'c1', 'delivered', '2017-03-01 10:00:00', '2017-03-15 00:00:00', 1, 0, '2017-03', 1, 1)"
    )


def add_item(conn, price=10.0, freight=2.0, item_id=1, product="p1"):
    conn.execute(
        "INSERT INTO order_items VALUES ('o1', ?, ?, 's1', '2017-03-05 00:00:00', ?, ?)",
        (item_id, product, price, freight),
    )


# ------------------------------------------------------------- constraints
def test_valid_rows_load(conn):
    seed(conn)
    add_item(conn)
    assert conn.execute("SELECT COUNT(*) FROM order_items").fetchone()[0] == 1


def test_item_price_must_be_positive(conn):
    seed(conn)
    with pytest.raises(sqlite3.IntegrityError):
        add_item(conn, price=0.0)


def test_item_freight_cannot_be_negative(conn):
    seed(conn)
    with pytest.raises(sqlite3.IntegrityError):
        add_item(conn, freight=-1.0)


def test_item_must_reference_an_existing_product(conn):
    seed(conn)
    with pytest.raises(sqlite3.IntegrityError):
        add_item(conn, product="missing_product")


def test_order_item_primary_key_is_unique(conn):
    seed(conn)
    add_item(conn, item_id=1)
    with pytest.raises(sqlite3.IntegrityError):
        add_item(conn, item_id=1)


def test_order_must_reference_an_existing_customer(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO orders (order_id, customer_id, order_status, order_purchase_timestamp, "
            "order_estimated_delivery_date, is_delivered_with_date, has_date_inconsistency, "
            "purchase_month, in_analysis_window, counts_as_sale) "
            "VALUES ('o9', 'no_such_customer', 'delivered', '2017-03-01 10:00:00', '2017-03-15 00:00:00', "
            "1, 0, '2017-03', 1, 1)"
        )


def test_review_score_must_be_between_1_and_5(conn):
    seed(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO order_reviews (order_id, review_id, review_score, review_creation_date, "
            "review_count, has_comment) VALUES ('o1', 'r1', 6, '2018-01-01 00:00:00', 1, 0)"
        )


def test_payment_value_cannot_be_negative(conn):
    seed(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO payments VALUES ('o1', 1, 'credit_card', 1, -5.0, 0)")


# ----------------------------------------------------------------- SQL files
def test_expected_number_of_queries_is_defined():
    assert len(KPI_QUERIES) == 13
    assert "monthly_kpis" in KPI_QUERIES
    assert len(DASHBOARD_QUERIES) == 3


@pytest.mark.parametrize("name", sorted(KPI_QUERIES))
def test_kpi_query_is_valid_sql_on_the_schema(conn, name):
    conn.execute(KPI_QUERIES[name]).fetchall()


@pytest.mark.parametrize("name", sorted(DASHBOARD_QUERIES))
def test_dashboard_query_is_valid_sql_on_the_schema(conn, name):
    conn.execute(DASHBOARD_QUERIES[name]).fetchall()


def test_parse_queries_splits_on_name_markers():
    text = "-- header comment\n-- name: first\nSELECT 1;\n\n-- name: second\nSELECT 2;\n"
    assert parse_queries(text) == {"first": "SELECT 1;", "second": "SELECT 2;"}


def test_parse_queries_rejects_text_without_markers():
    with pytest.raises(ValueError):
        parse_queries("SELECT 1;")