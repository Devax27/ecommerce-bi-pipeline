-- SQLite schema for the Olist e-commerce database.
-- Dates are stored as ISO-8601 text ('YYYY-MM-DD HH:MM:SS'); booleans as 0/1.

PRAGMA foreign_keys = ON;

CREATE TABLE customers (
    customer_id               TEXT PRIMARY KEY,   -- one per order
    customer_unique_id        TEXT NOT NULL,      -- the actual person
    customer_zip_code_prefix  INTEGER NOT NULL,
    customer_city             TEXT NOT NULL,
    customer_state            TEXT NOT NULL
);

CREATE TABLE sellers (
    seller_id               TEXT PRIMARY KEY,
    seller_zip_code_prefix  INTEGER NOT NULL,
    seller_city             TEXT NOT NULL,
    seller_state            TEXT NOT NULL
);

CREATE TABLE products (
    product_id                    TEXT PRIMARY KEY,
    product_category_name         TEXT,
    product_category_name_english TEXT NOT NULL,
    product_name_length           INTEGER,
    product_description_length   INTEGER,
    product_photos_qty            INTEGER,
    product_weight_g              REAL CHECK (product_weight_g IS NULL OR product_weight_g > 0),
    product_length_cm             REAL,
    product_height_cm             REAL,
    product_width_cm              REAL
);

CREATE TABLE orders (
    order_id                       TEXT PRIMARY KEY,
    customer_id                    TEXT NOT NULL REFERENCES customers (customer_id),
    order_status                   TEXT NOT NULL,
    order_purchase_timestamp       TEXT NOT NULL,
    order_approved_at              TEXT,
    order_delivered_carrier_date   TEXT,
    order_delivered_customer_date  TEXT,
    order_estimated_delivery_date  TEXT NOT NULL,
    is_delivered_with_date         INTEGER NOT NULL CHECK (is_delivered_with_date IN (0, 1)),
    has_date_inconsistency         INTEGER NOT NULL CHECK (has_date_inconsistency IN (0, 1)),
    delivery_days                  REAL,
    delivery_delay_days            INTEGER,
    purchase_month                 TEXT NOT NULL,
    in_analysis_window             INTEGER NOT NULL CHECK (in_analysis_window IN (0, 1)),
    counts_as_sale                 INTEGER NOT NULL CHECK (counts_as_sale IN (0, 1))
);

CREATE TABLE order_items (
    order_id             TEXT    NOT NULL REFERENCES orders (order_id),
    order_item_id        INTEGER NOT NULL,
    product_id           TEXT    NOT NULL REFERENCES products (product_id),
    seller_id            TEXT    NOT NULL REFERENCES sellers (seller_id),
    shipping_limit_date  TEXT    NOT NULL,
    price                REAL    NOT NULL CHECK (price > 0),
    freight_value        REAL    NOT NULL CHECK (freight_value >= 0),
    PRIMARY KEY (order_id, order_item_id)
);

CREATE TABLE payments (
    order_id              TEXT    NOT NULL REFERENCES orders (order_id),
    payment_sequential    INTEGER NOT NULL,
    payment_type          TEXT    NOT NULL,
    payment_installments  INTEGER NOT NULL,
    payment_value         REAL    NOT NULL CHECK (payment_value >= 0),
    is_zero_value         INTEGER NOT NULL CHECK (is_zero_value IN (0, 1)),
    PRIMARY KEY (order_id, payment_sequential)
);

-- One row per order (latest review). review_id is NOT unique in the source data.
CREATE TABLE order_reviews (
    order_id                TEXT PRIMARY KEY REFERENCES orders (order_id),
    review_id               TEXT NOT NULL,
    review_score            INTEGER NOT NULL CHECK (review_score BETWEEN 1 AND 5),
    review_comment_message  TEXT,
    review_creation_date    TEXT NOT NULL,
    review_answer_timestamp TEXT,
    review_count            INTEGER NOT NULL,
    has_comment             INTEGER NOT NULL CHECK (has_comment IN (0, 1))
);

CREATE TABLE zip_geolocation (
    zip_code_prefix  INTEGER PRIMARY KEY,
    lat              REAL NOT NULL,
    lng              REAL NOT NULL,
    n_points         INTEGER NOT NULL
);

CREATE INDEX idx_orders_customer     ON orders (customer_id);
CREATE INDEX idx_orders_month        ON orders (purchase_month);
CREATE INDEX idx_orders_status       ON orders (order_status);
CREATE INDEX idx_items_product       ON order_items (product_id);
CREATE INDEX idx_items_seller        ON order_items (seller_id);
CREATE INDEX idx_customers_unique    ON customers (customer_unique_id);
CREATE INDEX idx_customers_state     ON customers (customer_state);
CREATE INDEX idx_products_category   ON products (product_category_name_english);