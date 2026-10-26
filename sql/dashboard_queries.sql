-- Aggregate queries that feed the Streamlit dashboard. Run by src/build_dashboard_data.py.
-- Scope matches docs/kpi_definitions.md. Every column is additive, so the dashboard can
-- recombine rows when filtering (rates and averages are recomputed from sums).

-- name: monthly_state
SELECT o.purchase_month,
       c.customer_state,
       COUNT(DISTINCT o.order_id) AS orders,
       SUM(oi.price)              AS revenue,
       SUM(oi.freight_value)      AS freight
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
JOIN customers c    ON c.customer_id = o.customer_id
WHERE o.in_analysis_window = 1 AND o.counts_as_sale = 1
GROUP BY o.purchase_month, c.customer_state
ORDER BY o.purchase_month, c.customer_state;

-- name: delivery_month_state
SELECT o.purchase_month,
       c.customer_state,
       COUNT(*)                                                           AS delivered_orders,
       SUM(o.delivery_days)                                               AS total_delivery_days,
       SUM(CASE WHEN o.delivery_delay_days > 0 THEN 1 ELSE 0 END)         AS late_orders,
       COUNT(r.review_score)                                              AS reviews,
       SUM(r.review_score)                                                AS review_score_sum,
       COUNT(CASE WHEN o.delivery_delay_days > 0 THEN r.review_score END) AS late_reviews,
       SUM(CASE WHEN o.delivery_delay_days > 0 THEN r.review_score END)   AS late_review_sum
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
LEFT JOIN order_reviews r ON r.order_id = o.order_id
WHERE o.is_delivered_with_date = 1 AND o.in_analysis_window = 1
GROUP BY o.purchase_month, c.customer_state
ORDER BY o.purchase_month, c.customer_state;

-- name: category_month
SELECT o.purchase_month,
       p.product_category_name_english AS category,
       COUNT(DISTINCT o.order_id)      AS orders,
       COUNT(*)                        AS items,
       SUM(oi.price)                   AS revenue,
       COUNT(r.review_score)           AS review_item_rows,
       SUM(r.review_score)             AS review_score_sum
FROM order_items oi
JOIN orders o   ON o.order_id = oi.order_id
JOIN products p ON p.product_id = oi.product_id
LEFT JOIN order_reviews r ON r.order_id = o.order_id
WHERE o.in_analysis_window = 1 AND o.counts_as_sale = 1
GROUP BY o.purchase_month, p.product_category_name_english
ORDER BY o.purchase_month, category;