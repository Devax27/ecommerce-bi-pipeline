-- KPI queries for the Olist SQLite database. See docs/kpi_definitions.md.
-- Each query begins with a "-- name: <identifier>" line read by src/run_kpis.py.

-- name: revenue_reconciliation
SELECT o.counts_as_sale,
       COUNT(DISTINCT o.order_id)      AS orders_with_items,
       ROUND(SUM(oi.price), 2)         AS item_price,
       ROUND(SUM(oi.freight_value), 2) AS freight
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
GROUP BY o.counts_as_sale;

-- name: monthly_kpis
SELECT o.purchase_month,
       COUNT(DISTINCT o.order_id)                                   AS orders,
       ROUND(SUM(oi.price), 2)                                      AS revenue,
       ROUND(SUM(oi.price) / COUNT(DISTINCT o.order_id), 2)         AS avg_order_value,
       ROUND(SUM(oi.freight_value), 2)                              AS freight,
       COUNT(DISTINCT c.customer_unique_id)                         AS unique_customers
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
JOIN customers c    ON c.customer_id = o.customer_id
WHERE o.in_analysis_window = 1 AND o.counts_as_sale = 1
GROUP BY o.purchase_month
ORDER BY o.purchase_month;

-- name: monthly_growth
WITH monthly AS (
    SELECT o.purchase_month,
           COUNT(DISTINCT o.order_id) AS orders,
           SUM(oi.price)              AS revenue
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.order_id
    WHERE o.in_analysis_window = 1 AND o.counts_as_sale = 1
    GROUP BY o.purchase_month
)
SELECT purchase_month,
       orders,
       ROUND(revenue, 2) AS revenue,
       ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY purchase_month))
                   / LAG(revenue) OVER (ORDER BY purchase_month), 1) AS revenue_mom_pct,
       ROUND(100.0 * (orders - LAG(orders) OVER (ORDER BY purchase_month))
                   / LAG(orders) OVER (ORDER BY purchase_month), 1)  AS orders_mom_pct
FROM monthly
ORDER BY purchase_month;

-- name: delivery_overall
WITH base AS (
    SELECT delivery_days,
           delivery_delay_days,
           ROW_NUMBER() OVER (ORDER BY delivery_days) AS rn,
           COUNT(*) OVER ()                           AS n
    FROM orders
    WHERE is_delivered_with_date = 1 AND in_analysis_window = 1
)
SELECT MAX(n)                                                              AS delivered_orders,
       ROUND(AVG(delivery_days), 2)                                        AS avg_delivery_days,
       ROUND(AVG(CASE WHEN rn IN ((n + 1) / 2, (n + 2) / 2)
                      THEN delivery_days END), 2)                          AS median_delivery_days,
       ROUND(100.0 * AVG(delivery_delay_days > 0), 2)                      AS late_rate_pct
FROM base;

-- name: delivery_by_state
SELECT c.customer_state,
       COUNT(*)                                       AS delivered_orders,
       ROUND(AVG(o.delivery_days), 1)                 AS avg_delivery_days,
       ROUND(100.0 * AVG(o.delivery_delay_days > 0), 1) AS late_rate_pct
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
WHERE o.is_delivered_with_date = 1 AND o.in_analysis_window = 1
GROUP BY c.customer_state
HAVING COUNT(*) >= 100
ORDER BY avg_delivery_days DESC;

-- name: delivery_vs_reviews
SELECT CASE WHEN o.delivery_delay_days > 0 THEN 'late' ELSE 'on_time_or_early' END AS delivery_outcome,
       COUNT(*)                        AS orders,
       ROUND(AVG(r.review_score), 2)   AS avg_review_score
FROM orders o
JOIN order_reviews r ON r.order_id = o.order_id
WHERE o.is_delivered_with_date = 1 AND o.in_analysis_window = 1
GROUP BY delivery_outcome;

-- name: category_performance
WITH cat AS (
    SELECT p.product_category_name_english AS category,
           COUNT(DISTINCT o.order_id)      AS orders,
           ROUND(SUM(oi.price), 2)         AS revenue,
           ROUND(AVG(r.review_score), 2)   AS avg_review_score
    FROM order_items oi
    JOIN orders o   ON o.order_id = oi.order_id
    JOIN products p ON p.product_id = oi.product_id
    LEFT JOIN order_reviews r ON r.order_id = o.order_id
    WHERE o.in_analysis_window = 1 AND o.counts_as_sale = 1
    GROUP BY p.product_category_name_english
),
tot AS (SELECT SUM(revenue) AS total FROM cat)
SELECT cat.category,
       cat.orders,
       cat.revenue,
       ROUND(100.0 * cat.revenue / tot.total, 2) AS revenue_share_pct,
       cat.avg_review_score
FROM cat, tot
ORDER BY cat.revenue DESC
LIMIT 15;

-- name: lowest_rated_categories
SELECT p.product_category_name_english AS category,
       COUNT(DISTINCT o.order_id)      AS orders,
       ROUND(AVG(r.review_score), 2)   AS avg_review_score
FROM order_items oi
JOIN orders o   ON o.order_id = oi.order_id
JOIN products p ON p.product_id = oi.product_id
JOIN order_reviews r ON r.order_id = o.order_id
WHERE o.in_analysis_window = 1 AND o.counts_as_sale = 1
GROUP BY p.product_category_name_english
HAVING COUNT(DISTINCT o.order_id) >= 300
ORDER BY avg_review_score ASC
LIMIT 10;

-- name: top_sellers
SELECT s.seller_id,
       s.seller_state,
       COUNT(DISTINCT o.order_id)    AS orders,
       ROUND(SUM(oi.price), 2)       AS revenue,
       ROUND(AVG(r.review_score), 2) AS avg_review_score
FROM order_items oi
JOIN orders o  ON o.order_id = oi.order_id
JOIN sellers s ON s.seller_id = oi.seller_id
LEFT JOIN order_reviews r ON r.order_id = o.order_id
WHERE o.in_analysis_window = 1 AND o.counts_as_sale = 1
GROUP BY s.seller_id, s.seller_state
ORDER BY revenue DESC
LIMIT 15;

-- name: seller_concentration
WITH s AS (
    SELECT oi.seller_id, SUM(oi.price) AS rev
    FROM order_items oi
    JOIN orders o ON o.order_id = oi.order_id
    WHERE o.in_analysis_window = 1 AND o.counts_as_sale = 1
    GROUP BY oi.seller_id
),
ranked AS (
    SELECT rev,
           ROW_NUMBER() OVER (ORDER BY rev DESC) AS rk,
           COUNT(*) OVER ()                      AS n
    FROM s
)
SELECT MAX(n) AS active_sellers,
       ROUND(100.0 * SUM(CASE WHEN rk <= 10 THEN rev END) / SUM(rev), 1)     AS top10_sellers_share_pct,
       ROUND(100.0 * SUM(CASE WHEN rk <= n / 10 THEN rev END) / SUM(rev), 1) AS top_decile_sellers_share_pct
FROM ranked;

-- name: repeat_customers
WITH per_person AS (
    SELECT c.customer_unique_id, COUNT(DISTINCT o.order_id) AS n_orders
    FROM orders o
    JOIN customers c ON c.customer_id = o.customer_id
    WHERE o.in_analysis_window = 1 AND o.counts_as_sale = 1
    GROUP BY c.customer_unique_id
)
SELECT COUNT(*)                                   AS customers,
       SUM(n_orders > 1)                          AS repeat_customers,
       ROUND(100.0 * SUM(n_orders > 1) / COUNT(*), 2) AS repeat_rate_pct,
       ROUND(AVG(n_orders), 3)                    AS avg_orders_per_customer
FROM per_person;

-- name: payment_mix
SELECT p.payment_type,
       COUNT(DISTINCT p.order_id)  AS orders,
       ROUND(SUM(p.payment_value), 2) AS payment_value
FROM payments p
JOIN orders o ON o.order_id = p.order_id
WHERE o.in_analysis_window = 1 AND o.counts_as_sale = 1
GROUP BY p.payment_type
ORDER BY payment_value DESC;

-- name: revenue_by_state
SELECT c.customer_state,
       COUNT(DISTINCT o.order_id)                           AS orders,
       ROUND(SUM(oi.price), 2)                              AS revenue,
       ROUND(SUM(oi.price) / COUNT(DISTINCT o.order_id), 2) AS avg_order_value
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
JOIN customers c    ON c.customer_id = o.customer_id
WHERE o.in_analysis_window = 1 AND o.counts_as_sale = 1
GROUP BY c.customer_state
ORDER BY revenue DESC
LIMIT 10;