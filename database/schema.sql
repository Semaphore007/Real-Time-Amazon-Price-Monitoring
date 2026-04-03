-- =============================================================================
-- E-Commerce Price Monitoring System — PostgreSQL Schema
-- =============================================================================
-- Design goals:
--   1. Normalized (3NF) relational schema
--   2. Comprehensive indexing for fast point-lookups AND range scans
--   3. Full historical data support (append-only time-series tables)
--   4. Analytics-ready materialized views and helper functions
--   5. Row-level alerting with flexible condition storage (JSONB)
-- =============================================================================

-- Enable useful extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "btree_gin";  -- GIN on composite types
CREATE EXTENSION IF NOT EXISTS "pg_trgm";    -- trigram full-text search on titles

-- ---------------------------------------------------------------------------
-- 1. PRODUCTS
--    Core catalogue table; one row per unique ASIN.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id              SERIAL          PRIMARY KEY,
    asin            VARCHAR(32)     NOT NULL,
    title           TEXT            NOT NULL,
    brand           VARCHAR(120),
    category        VARCHAR(120),
    sub_category    VARCHAR(120),
    image_url       TEXT,
    product_url     TEXT,
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_products_asin UNIQUE (asin)
);

-- Fast lookup by ASIN (most frequent join key)
CREATE INDEX IF NOT EXISTS idx_products_asin         ON products (asin);
-- Category-level analytics (GROUP BY category)
CREATE INDEX IF NOT EXISTS idx_products_category     ON products (category);
-- Full-text search on title using trigrams
CREATE INDEX IF NOT EXISTS idx_products_title_trgm   ON products USING GIN (title gin_trgm_ops);

-- Auto-update updated_at on any row change
CREATE OR REPLACE FUNCTION fn_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_products_updated_at ON products;
CREATE TRIGGER trg_products_updated_at
    BEFORE UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- ---------------------------------------------------------------------------
-- 2. SELLERS
--    Deduplicated seller registry. seller_id is the marketplace's native ID.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sellers (
    id              SERIAL          PRIMARY KEY,
    seller_id       VARCHAR(64)     NOT NULL,   -- Amazon seller ID (e.g. A1B2C3...)
    name            VARCHAR(255)    NOT NULL,
    rating          NUMERIC(3,2),
    review_count    INTEGER,
    fulfillment_type VARCHAR(40),               -- 'FBA' | 'FBM' | 'Amazon'
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_sellers_seller_id UNIQUE (seller_id)
);

CREATE INDEX IF NOT EXISTS idx_sellers_seller_id ON sellers (seller_id);
CREATE INDEX IF NOT EXISTS idx_sellers_name      ON sellers USING GIN (name gin_trgm_ops);

DROP TRIGGER IF EXISTS trg_sellers_updated_at ON sellers;
CREATE TRIGGER trg_sellers_updated_at
    BEFORE UPDATE ON sellers
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- ---------------------------------------------------------------------------
-- 3. LOCATIONS
--    Delivery-location dimension (pincode → city → state).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS locations (
    id          SERIAL      PRIMARY KEY,
    pincode     VARCHAR(12) NOT NULL,
    city        VARCHAR(120),
    state       VARCHAR(120),
    country     VARCHAR(60) NOT NULL DEFAULT 'India',

    CONSTRAINT uq_locations_pincode_city UNIQUE (pincode, city)
);

CREATE INDEX IF NOT EXISTS idx_locations_pincode ON locations (pincode);
CREATE INDEX IF NOT EXISTS idx_locations_state   ON locations (state);

-- ---------------------------------------------------------------------------
-- 4. LISTINGS  (current snapshot of every ASIN × seller offer)
--    Each row = one seller's live offer for one product at one location.
--    is_buybox = TRUE for the seller currently winning the Buy Box.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS listings (
    id              BIGSERIAL       PRIMARY KEY,
    asin            VARCHAR(32)     NOT NULL REFERENCES products (asin) ON DELETE CASCADE,
    seller_id       VARCHAR(64)     NOT NULL REFERENCES sellers (seller_id) ON DELETE CASCADE,
    location_id     INTEGER         REFERENCES locations (id) ON DELETE SET NULL,
    price           NUMERIC(12,2)   NOT NULL,
    mrp             NUMERIC(12,2),                  -- Maximum Retail Price
    discount_pct    NUMERIC(5,2)    GENERATED ALWAYS AS (
                        CASE WHEN mrp > 0
                             THEN ROUND((mrp - price) / mrp * 100, 2)
                             ELSE NULL END
                    ) STORED,
    currency        CHAR(3)         NOT NULL DEFAULT 'INR',
    is_buybox       BOOLEAN         NOT NULL DEFAULT FALSE,
    is_fba          BOOLEAN         NOT NULL DEFAULT FALSE,
    availability    VARCHAR(60),
    delivery_days   SMALLINT,
    seller_rating   NUMERIC(3,2),
    timestamp       TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- Primary access pattern: latest offers for a product
CREATE INDEX IF NOT EXISTS idx_listings_asin_ts         ON listings (asin, timestamp DESC);
-- Buy-box monitoring
CREATE INDEX IF NOT EXISTS idx_listings_buybox          ON listings (asin, is_buybox, timestamp DESC);
-- Seller-centric queries
CREATE INDEX IF NOT EXISTS idx_listings_seller_asin     ON listings (seller_id, asin, timestamp DESC);
-- Price range / cheapest offer
CREATE INDEX IF NOT EXISTS idx_listings_price           ON listings (asin, price);
-- Recent data partial index (last 90 days) — accelerates dashboard queries
CREATE INDEX IF NOT EXISTS idx_listings_recent          ON listings (asin, timestamp DESC)
    WHERE timestamp >= NOW() - INTERVAL '90 days';

-- ---------------------------------------------------------------------------
-- 5. PRICE_HISTORY  (immutable, append-only time-series)
--    One row per scrape event for the Buy-Box / representative price.
--    Kept separate from listings so it can be partitioned independently.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS price_history (
    id              BIGSERIAL       PRIMARY KEY,
    asin            VARCHAR(32)     NOT NULL REFERENCES products (asin) ON DELETE CASCADE,
    seller_id       VARCHAR(64)     REFERENCES sellers (seller_id) ON DELETE SET NULL,
    location_id     INTEGER         REFERENCES locations (id) ON DELETE SET NULL,
    price           NUMERIC(12,2)   NOT NULL,
    mrp             NUMERIC(12,2),
    currency        CHAR(3)         NOT NULL DEFAULT 'INR',
    availability    VARCHAR(60),
    rating          NUMERIC(3,2),
    review_count    INTEGER,
    is_fba          BOOLEAN         NOT NULL DEFAULT FALSE,
    source          VARCHAR(60)     NOT NULL DEFAULT 'scraper',  -- 'scraper'|'api'|'manual'
    timestamp       TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- Most-common access: price trend for a product over time
CREATE INDEX IF NOT EXISTS idx_ph_asin_ts           ON price_history (asin, timestamp DESC);
-- Seller's historical pricing (competitive analysis)
CREATE INDEX IF NOT EXISTS idx_ph_seller_asin_ts    ON price_history (seller_id, asin, timestamp DESC);
-- Time-window aggregations (daily/weekly averages)
CREATE INDEX IF NOT EXISTS idx_ph_ts                ON price_history (timestamp DESC);
-- Location-scoped queries
CREATE INDEX IF NOT EXISTS idx_ph_location_asin     ON price_history (location_id, asin);

-- ---------------------------------------------------------------------------
-- 6. BUY_BOX_HISTORY  (who owned the buy box and when)
--    Derived from listings but stored separately for fast ownership queries.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS buy_box_history (
    id              BIGSERIAL       PRIMARY KEY,
    asin            VARCHAR(32)     NOT NULL REFERENCES products (asin) ON DELETE CASCADE,
    seller_id       VARCHAR(64)     NOT NULL REFERENCES sellers (seller_id) ON DELETE CASCADE,
    location_id     INTEGER         REFERENCES locations (id) ON DELETE SET NULL,
    price           NUMERIC(12,2)   NOT NULL,
    captured_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bbh_asin_ts       ON buy_box_history (asin, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_bbh_seller_asin   ON buy_box_history (seller_id, asin, captured_at DESC);

-- ---------------------------------------------------------------------------
-- 7. ALERT_RULES  (user-configured thresholds)
--    condition is a JSONB document — flexible for any rule type:
--      {"type": "price_drop",    "threshold_pct": 10}
--      {"type": "price_above",   "value": 999.00}
--      {"type": "buybox_change", "seller_id": "A1B2C3"}
--      {"type": "oos",           "consecutive_checks": 3}
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alert_rules (
    id              SERIAL          PRIMARY KEY,
    asin            VARCHAR(32)     NOT NULL REFERENCES products (asin) ON DELETE CASCADE,
    seller_id       VARCHAR(64)     REFERENCES sellers (seller_id) ON DELETE CASCADE,
    condition       JSONB           NOT NULL,
    severity        VARCHAR(20)     NOT NULL DEFAULT 'info'
                                    CHECK (severity IN ('info','warning','critical')),
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    notify_email    VARCHAR(255),
    notify_webhook  TEXT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alert_rules_asin        ON alert_rules (asin) WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_alert_rules_condition   ON alert_rules USING GIN (condition);

DROP TRIGGER IF EXISTS trg_alert_rules_updated_at ON alert_rules;
CREATE TRIGGER trg_alert_rules_updated_at
    BEFORE UPDATE ON alert_rules
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- ---------------------------------------------------------------------------
-- 8. ALERTS  (triggered alert events — one row per firing)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alerts (
    id              BIGSERIAL       PRIMARY KEY,
    rule_id         INTEGER         REFERENCES alert_rules (id) ON DELETE SET NULL,
    asin            VARCHAR(32)     NOT NULL,
    seller_id       VARCHAR(64),
    condition       JSONB           NOT NULL,   -- snapshot of the rule condition at fire time
    message         TEXT            NOT NULL,
    severity        VARCHAR(20)     NOT NULL DEFAULT 'info',
    old_value       NUMERIC(12,2),             -- previous price / metric
    new_value       NUMERIC(12,2),             -- triggering price / metric
    triggered_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by VARCHAR(120)
);

CREATE INDEX IF NOT EXISTS idx_alerts_asin_ts      ON alerts (asin, triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_rule_id      ON alerts (rule_id, triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_severity_ts  ON alerts (severity, triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_unacked      ON alerts (triggered_at DESC)
    WHERE acknowledged_at IS NULL;

-- ---------------------------------------------------------------------------
-- 9. SCRAPE_JOBS  (audit log for every scrape run)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scrape_jobs (
    id              BIGSERIAL       PRIMARY KEY,
    asin            VARCHAR(32),
    status          VARCHAR(20)     NOT NULL DEFAULT 'pending'
                                    CHECK (status IN ('pending','running','success','failed','retrying')),
    attempts        SMALLINT        NOT NULL DEFAULT 0,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    duration_ms     INTEGER         GENERATED ALWAYS AS (
                        CASE WHEN started_at IS NOT NULL AND finished_at IS NOT NULL
                             THEN EXTRACT(EPOCH FROM (finished_at - started_at))::INTEGER * 1000
                             ELSE NULL END
                    ) STORED,
    proxy_used      VARCHAR(120),
    error_message   TEXT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scrape_jobs_asin_ts   ON scrape_jobs (asin, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_scrape_jobs_status    ON scrape_jobs (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_scrape_jobs_failed    ON scrape_jobs (created_at DESC)
    WHERE status = 'failed';

-- =============================================================================
-- ANALYTICS VIEWS
-- =============================================================================

-- ---------------------------------------------------------------------------
-- V1: Latest price per ASIN (current Buy Box price)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_latest_price AS
SELECT DISTINCT ON (ph.asin)
    ph.asin,
    p.title,
    p.category,
    ph.price,
    ph.currency,
    ph.seller_id,
    s.name          AS seller_name,
    ph.availability,
    ph.timestamp    AS captured_at
FROM price_history ph
JOIN products  p ON p.asin = ph.asin
LEFT JOIN sellers s ON s.seller_id = ph.seller_id
ORDER BY ph.asin, ph.timestamp DESC;

-- ---------------------------------------------------------------------------
-- V2: Price trend (daily OHLC) per ASIN — analytics-friendly
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_daily_price_ohlc AS
SELECT
    asin,
    DATE_TRUNC('day', timestamp)    AS day,
    MIN(price)                      AS low,
    MAX(price)                      AS high,
    -- FIRST / LAST price of the day
    (ARRAY_AGG(price ORDER BY timestamp ASC))[1]  AS open,
    (ARRAY_AGG(price ORDER BY timestamp DESC))[1] AS close,
    AVG(price)                      AS avg_price,
    COUNT(*)                        AS sample_count
FROM price_history
GROUP BY asin, DATE_TRUNC('day', timestamp);

-- ---------------------------------------------------------------------------
-- V3: Current Buy Box winners with seller detail
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_buybox_current AS
SELECT DISTINCT ON (l.asin)
    l.asin,
    p.title,
    p.category,
    l.seller_id,
    s.name          AS seller_name,
    s.fulfillment_type,
    l.price,
    l.mrp,
    l.discount_pct,
    l.currency,
    l.is_fba,
    l.timestamp     AS as_of
FROM listings l
JOIN products p ON p.asin = l.asin
LEFT JOIN sellers s ON s.seller_id = l.seller_id
WHERE l.is_buybox = TRUE
ORDER BY l.asin, l.timestamp DESC;

-- ---------------------------------------------------------------------------
-- V4: Price drop events (consecutive readings where price fell > 5%)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_price_drops AS
WITH ranked AS (
    SELECT
        asin,
        price,
        timestamp,
        LAG(price) OVER (PARTITION BY asin ORDER BY timestamp) AS prev_price
    FROM price_history
)
SELECT
    asin,
    prev_price,
    price                               AS new_price,
    ROUND((prev_price - price) / prev_price * 100, 2) AS drop_pct,
    timestamp
FROM ranked
WHERE prev_price IS NOT NULL
  AND price < prev_price
  AND (prev_price - price) / prev_price > 0.05
ORDER BY drop_pct DESC;

-- ---------------------------------------------------------------------------
-- V5: Seller competitive summary (win-rate, avg price per ASIN)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_seller_competitiveness AS
SELECT
    l.asin,
    l.seller_id,
    s.name                          AS seller_name,
    COUNT(*)                        AS total_snapshots,
    SUM(l.is_buybox::INT)           AS buybox_wins,
    ROUND(
        SUM(l.is_buybox::INT)::NUMERIC / NULLIF(COUNT(*),0) * 100, 2
    )                               AS buybox_win_rate_pct,
    ROUND(AVG(l.price), 2)          AS avg_price,
    MIN(l.price)                    AS min_price,
    MAX(l.price)                    AS max_price
FROM listings l
LEFT JOIN sellers s ON s.seller_id = l.seller_id
GROUP BY l.asin, l.seller_id, s.name;

-- =============================================================================
-- MATERIALIZED VIEW — refreshed by scheduler (e.g. every hour)
-- =============================================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS mvw_category_price_summary AS
SELECT
    p.category,
    COUNT(DISTINCT p.asin)              AS product_count,
    ROUND(AVG(lp.price), 2)             AS avg_current_price,
    MIN(lp.price)                       AS min_price,
    MAX(lp.price)                       AS max_price,
    NOW()                               AS refreshed_at
FROM products p
JOIN vw_latest_price lp ON lp.asin = p.asin
GROUP BY p.category
WITH DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mvw_cat_summary_cat
    ON mvw_category_price_summary (category);

-- Refresh command (run from scheduler):
-- REFRESH MATERIALIZED VIEW CONCURRENTLY mvw_category_price_summary;

-- =============================================================================
-- HELPER FUNCTION: get price history for an ASIN in a time window
-- =============================================================================
CREATE OR REPLACE FUNCTION fn_price_history(
    p_asin      VARCHAR,
    p_from      TIMESTAMPTZ DEFAULT NOW() - INTERVAL '30 days',
    p_to        TIMESTAMPTZ DEFAULT NOW()
)
RETURNS TABLE (
    asin        VARCHAR,
    price       NUMERIC,
    seller_id   VARCHAR,
    seller_name VARCHAR,
    timestamp   TIMESTAMPTZ
)
LANGUAGE sql STABLE AS $$
    SELECT
        ph.asin,
        ph.price,
        ph.seller_id,
        s.name,
        ph.timestamp
    FROM price_history ph
    LEFT JOIN sellers s ON s.seller_id = ph.seller_id
    WHERE ph.asin = p_asin
      AND ph.timestamp BETWEEN p_from AND p_to
    ORDER BY ph.timestamp DESC;
$$;

-- =============================================================================
-- HELPER FUNCTION: fire an alert
-- =============================================================================
CREATE OR REPLACE FUNCTION fn_fire_alert(
    p_rule_id   INTEGER,
    p_asin      VARCHAR,
    p_seller_id VARCHAR,
    p_condition JSONB,
    p_message   TEXT,
    p_severity  VARCHAR,
    p_old_val   NUMERIC,
    p_new_val   NUMERIC
)
RETURNS BIGINT LANGUAGE plpgsql AS $$
DECLARE
    v_id BIGINT;
BEGIN
    INSERT INTO alerts (rule_id, asin, seller_id, condition, message,
                        severity, old_value, new_value, triggered_at)
    VALUES (p_rule_id, p_asin, p_seller_id, p_condition, p_message,
            p_severity, p_old_val, p_new_val, NOW())
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

-- =============================================================================
-- SEED: default product categories (optional lookup table)
-- =============================================================================
CREATE TABLE IF NOT EXISTS categories (
    id      SERIAL      PRIMARY KEY,
    name    VARCHAR(120) NOT NULL UNIQUE,
    parent  VARCHAR(120)
);

INSERT INTO categories (name, parent) VALUES
    ('Industrial & Scientific', NULL),
    ('Bearings',                'Industrial & Scientific'),
    ('Electronics',             NULL),
    ('Home & Kitchen',          NULL),
    ('Sports & Outdoors',       NULL)
ON CONFLICT (name) DO NOTHING;

-- =============================================================================
-- GRANTS (adjust roles to your deployment)
-- =============================================================================
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_role;
-- GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO app_role;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_role;

-- =============================================================================
-- END OF SCHEMA
-- =============================================================================
