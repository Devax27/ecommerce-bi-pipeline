# Cleaning decisions

Source: Olist Brazilian E-Commerce Public Dataset (Kaggle, CC BY-NC-SA 4.0).
Evidence: `docs/data_profile.txt` and `src/investigate_anomalies.py`.
Raw files in `data/raw` are never modified; `src/clean_data.py` writes Parquet files to `data/processed`.

| Issue (evidence) | Decision |
|---|---|
| Same `review_id` reused across different orders (789 ids); 547 orders have 2-3 reviews | One row per order in `order_reviews` (latest review), plus `review_count` |
| 775 orders have no item rows (603 unavailable, 164 canceled, 8 other) | Kept in `orders`; they contribute 0 revenue |
| 8 delivered orders lack a delivery date; 6 canceled orders have one | Rows kept; `is_delivered_with_date` flag; delivery metrics use only flagged rows |
| 23 orders delivered before carrier pickup | Kept; `has_date_inconsistency` flag |
| 9 payments with value 0 (6 voucher, 3 not_defined) | Kept; `is_zero_value` flag |
| Items price+freight total 15,843,409.78 vs payments total 15,846,280.17 (389 of 98,665 orders differ by > 0.01; cause not investigated) | Revenue = SUM(item price) for orders that are not canceled/unavailable; freight reported separately |
| 13 products lack an English category | 2 manual translations (my own, not from the dataset); the kitchen one is an approximation |
| 610 products have no category | Category = `unknown` |
| 4 products have weight 0 | Weight set to missing |
| Misspelled columns `product_name_lenght`, `product_description_lenght` | Renamed to `..._length` |
| 2016 sparse (no 2016-11 orders); 2018-09 and 2018-10 nearly empty | `in_analysis_window` = purchases from 2017-01-01 to 2018-08-31 |
| Geolocation: multiple points per zip prefix; 42 points outside rough Brazil bounding box | Drop out-of-box points; one row per prefix using median lat/lng |
| Customer identity | `customer_id` is per order; use `customer_unique_id` (96,096 people) for repeat-purchase analysis |