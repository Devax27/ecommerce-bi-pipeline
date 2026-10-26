# KPI definitions

All sales KPIs use orders where `counts_as_sale = 1` (status not canceled/unavailable) and `in_analysis_window = 1`
(purchases 2017-01-01 to 2018-08-31, the complete months). Queries live in `sql/kpi_queries.sql`.

| KPI | Definition |
|---|---|
| Revenue | SUM(order_items.price). Freight is reported separately, never included. |
| Orders | COUNT(DISTINCT order_id) among orders that have item rows. |
| Average order value (AOV) | Revenue / Orders. |
| Delivery days | Purchase timestamp to customer delivery timestamp, only for delivered orders with a delivery date. |
| Late delivery rate | Share of those orders delivered after the estimated delivery date (calendar-day comparison). |
| Repeat customer rate | Share of unique people (`customer_unique_id`) with 2 or more sales orders in the window. |
| Category | `product_category_name_english` ('unknown' if the product has no category). |
| Review score | One review per order (the latest). In category and seller tables it is averaged over item rows, so an order with several items counts once per item. |
| Payment mix | An order paid with several payment types counts once in each type. |