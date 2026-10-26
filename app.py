"""Streamlit dashboard for the Olist e-commerce BI project.

Run from the project root:  streamlit run app.py
Reads only dashboard_data/*.csv, so it needs neither the raw data nor the database.
"""
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from src import dashboard_metrics as dm

DATA_DIR = Path(__file__).resolve().parent / "dashboard_data"
REQUIRED_FILES = [
    "monthly_state",
    "delivery_month_state",
    "category_month",
    "top_sellers",
    "seller_concentration",
    "repeat_customers",
]

st.set_page_config(page_title="Olist E-commerce BI", page_icon="📦", layout="wide")


@st.cache_data
def load_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / f"{name}.csv")


def money(value: float | None, decimals: int = 0) -> str:
    return "n/a" if value is None else f"R$ {value:,.{decimals}f}"


def number(value: float | None, decimals: int = 0) -> str:
    return "n/a" if value is None else f"{value:,.{decimals}f}"


def show(fig) -> None:
    """Render a Plotly figure at full container width, without touch-zoom or a toolbar over the title."""
    fig.update_layout(margin={"l": 10, "r": 10, "t": 50, "b": 10}, dragmode=False)
    config = {"displayModeBar": False, "scrollZoom": False}
    try:
        st.plotly_chart(fig, width="stretch", config=config)
    except TypeError:  # older Streamlit versions
        st.plotly_chart(fig, use_container_width=True, config=config)


# ---------------------------------------------------------------- load data
missing = [n for n in REQUIRED_FILES if not (DATA_DIR / f"{n}.csv").exists()]
if missing:
    st.error(f"Missing data files in dashboard_data/: {missing}. Run `python src/build_dashboard_data.py`.")
    st.stop()

monthly_state = load_csv("monthly_state")
delivery = load_csv("delivery_month_state")
category = load_csv("category_month")
top_sellers = load_csv("top_sellers")
concentration = load_csv("seller_concentration").iloc[0]
repeat = load_csv("repeat_customers").iloc[0]

# ------------------------------------------------------------------ sidebar
months = sorted(monthly_state["purchase_month"].unique())
all_states = sorted(monthly_state["customer_state"].unique())

st.sidebar.header("Filters")
start, end = st.sidebar.select_slider("Purchase months", options=months, value=(months[0], months[-1]))
selected_states = st.sidebar.multiselect("Customer states", all_states, default=all_states)
if not selected_states:
    st.warning("Select at least one state in the sidebar.")
    st.stop()
state_filter = None if len(selected_states) == len(all_states) else selected_states

st.sidebar.caption(
    "Scope: orders that count as sales (not canceled/unavailable), placed 2017-01 to 2018-08, the complete months. "
    "Revenue is item price in Brazilian reais (R$), excluding freight."
)

sales_f = dm.filter_data(monthly_state, start, end, state_filter)
delivery_f = dm.filter_data(delivery, start, end, state_filter)
category_f = dm.filter_data(category, start, end)  # category table has no state column

st.title("Olist e-commerce: business dashboard")
st.caption(f"Showing {start} to {end} | {len(selected_states)} of {len(all_states)} states")

overview_tab, delivery_tab, products_tab, about_tab = st.tabs(
    ["Overview", "Delivery & satisfaction", "Categories & sellers", "About"]
)

# ----------------------------------------------------------------- overview
with overview_tab:
    s = dm.sales_summary(sales_f)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Revenue", money(s["revenue"]))
    c2.metric("Orders", number(s["orders"]))
    c3.metric("Average order value", money(s["avg_order_value"], 2))
    c4.metric("Freight charged", money(s["freight"]))

    if s["orders"] == 0:
        st.info("No orders match the current filters.")
    else:
        monthly = dm.monthly_sales(sales_f)
        left, right = st.columns(2)
        with left:
            fig = px.line(monthly, x="purchase_month", y="revenue", markers=True,
                          title="Monthly revenue (R$)", labels={"purchase_month": "Month", "revenue": "Revenue (R$)"})
            fig.update_xaxes(type="category")
            show(fig)
        with right:
            fig = px.bar(monthly, x="purchase_month", y="orders", title="Monthly orders",
                         labels={"purchase_month": "Month", "orders": "Orders"})
            fig.update_xaxes(type="category")
            show(fig)

        top_states = dm.state_sales(sales_f).head(10).sort_values("revenue")
        fig = px.bar(top_states, x="revenue", y="customer_state", orientation="h",
                     title="Top 10 states by revenue (R$)", labels={"revenue": "Revenue (R$)", "customer_state": "State"})
        show(fig)
    st.caption("Peak day in the data: 2017-11-24 (1,166 orders), consistent with Black Friday; the dataset has no promotion flag, so that link is likely, not proven.")

# ----------------------------------------------------------------- delivery
with delivery_tab:
    d = dm.delivery_summary(delivery_f)
    if d["delivered_orders"] == 0:
        st.info("No delivered orders match the current filters.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Delivered orders", number(d["delivered_orders"]))
        c2.metric("Average delivery time", f"{number(d['avg_delivery_days'], 2)} days")
        c3.metric("Late delivery rate", f"{number(d['late_rate_pct'], 2)}%")
        c4.metric("Review score: late vs on-time",
                  f"{number(d['avg_score_late'], 2)} vs {number(d['avg_score_on_time'], 2)}")

        left, right = st.columns(2)
        with left:
            by_state = dm.delivery_by_state(delivery_f, min_orders=100)
            if by_state.empty:
                st.info("No state has 100 or more delivered orders in this selection.")
            else:
                fig = px.bar(by_state.sort_values("late_rate_pct"), x="late_rate_pct", y="customer_state",
                orientation="h", title="Late delivery rate by state (%)",
                labels={"late_rate_pct": "Late rate (%)", "customer_state": "State"})
                fig.update_yaxes(dtick=1)  # label every state, not every other one
                fig.update_layout(height=max(350, 26 * len(by_state) + 120))
                show(fig)
        with right:
            md = dm.monthly_delivery(delivery_f)
            fig = px.line(md, x="purchase_month", y="late_rate_pct", markers=True,
                          title="Late delivery rate by purchase month (%)",
                          labels={"purchase_month": "Month", "late_rate_pct": "Late rate (%)"})
            fig.update_xaxes(type="category")
            show(fig)
        st.caption(
            "Late = delivered after the estimated date (calendar-day comparison). States with fewer than 100 "
            "delivered orders in the selection are hidden. Late orders have much lower review scores; this is an "
            "association, not proof that lateness alone causes the low scores."
        )

# ---------------------------------------------------------------- products
with products_tab:
    st.subheader("Categories")
    st.caption("The state filter does not apply here: the category table is aggregated by month and category only.")
    top_n = st.slider("Categories to show", min_value=5, max_value=20, value=10)
    cats = dm.category_summary(category_f, top_n=top_n)
    if cats.empty:
        st.info("No category data for the selected months.")
    else:
        fig = px.bar(cats.sort_values("revenue"), x="revenue", y="category", orientation="h",
                     color="avg_review_score", color_continuous_scale="RdYlGn",range_color=(3.5, 4.5),
                     title="Top categories by revenue (colour = average review score)",
                     labels={"revenue": "Revenue (R$)", "category": "Category", "avg_review_score": "Avg review"})
        show(fig)
        table = cats.rename(columns={
            "category": "Category", "orders": "Orders", "revenue": "Revenue (R$)",
            "revenue_share_pct": "Revenue share (%)", "avg_review_score": "Avg review score",
        }).round(2)
        st.dataframe(table, hide_index=True)

    st.subheader("Sellers and repeat purchases (full period, not affected by filters)")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active sellers", number(concentration["active_sellers"]))
    c2.metric("Top 10% of sellers: revenue share", f"{number(concentration['top_decile_sellers_share_pct'], 1)}%")
    c3.metric("Repeat customer rate", f"{number(repeat['repeat_rate_pct'], 2)}%")
    c4.metric("Orders per customer", number(repeat["avg_orders_per_customer"], 3))

    sellers = top_sellers.copy()
    sellers["seller_id"] = sellers["seller_id"].str[:8] + "..."
    sellers = sellers.rename(columns={
        "seller_id": "Seller (shortened id)", "seller_state": "State", "orders": "Orders",
        "revenue": "Revenue (R$)", "avg_review_score": "Avg review score",
    })
    st.dataframe(sellers, hide_index=True)

# -------------------------------------------------------------------- about
with about_tab:
    st.markdown(
        """
### About this dashboard
An end-to-end BI pipeline on the Olist Brazilian e-commerce dataset: raw CSVs -> cleaning (Python) ->
SQLite database and KPI queries (SQL) -> validated aggregate tables -> this Streamlit app.

**Definitions**
- **Scope:** orders not canceled or unavailable, purchased 2017-01 to 2018-08 (the complete months).
- **Revenue:** sum of item price, excluding freight. Freight is shown separately.
- **Average order value:** revenue / orders.
- **Late delivery:** delivered after the estimated delivery date; delivery metrics use delivered orders with a recorded delivery date.
- **Review score:** one review per order (the latest). In category and seller tables it is averaged over item rows.
- **Repeat customer rate:** people (`customer_unique_id`) with 2 or more orders in the window.

**Limitations**
- Static historical data (2016-2018) from one marketplace; it says nothing about the current market.
- Associations shown here (for example late delivery and low reviews) are not proof of causation.
- Timestamps are used as recorded; the dataset does not document their time zone.

**Data attribution:** Brazilian E-Commerce Public Dataset by Olist
([Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)), licensed under
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). The tables in this app are modified
aggregates of that data, shared under the same license for non-commercial use.
"""
    )