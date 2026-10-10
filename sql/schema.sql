-- Reference DDL (tables are created automatically by etl/load.py via SQLAlchemy).
CREATE TABLE IF NOT EXISTS raw_products (          -- temporary staging, reloaded every run
    id TEXT, title TEXT, price TEXT, description TEXT, category TEXT,
    image TEXT, rating_rate TEXT, rating_count TEXT,
    extracted_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS transformed_products (  -- main analytics table
    id                 INTEGER PRIMARY KEY,
    title              TEXT           NOT NULL,
    category           VARCHAR(64)    NOT NULL,
    price              NUMERIC(10, 2) NOT NULL,
    price_tier         VARCHAR(16)    NOT NULL,     -- budget / mid / premium
    description        TEXT,
    description_length INTEGER,
    image_url          TEXT,
    rating_rate        DOUBLE PRECISION,
    rating_count       INTEGER,
    popularity_score   DOUBLE PRECISION,            -- rating * log10(1 + reviews)
    is_highly_rated    BOOLEAN,                     -- rating >= 4.0
    loaded_at          TIMESTAMPTZ    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_transformed_products_category ON transformed_products (category);

CREATE TABLE IF NOT EXISTS rejected_products (     -- data-quality quarantine
    rejected_id BIGSERIAL PRIMARY KEY, run_id INTEGER, record_id TEXT,
    reason TEXT NOT NULL, payload TEXT, rejected_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_runs (         -- observability / audit
    run_id SERIAL PRIMARY KEY, started_at TIMESTAMPTZ NOT NULL, finished_at TIMESTAMPTZ,
    status VARCHAR(16) NOT NULL, rows_extracted INTEGER, rows_loaded INTEGER,
    rows_rejected INTEGER, error_message TEXT
);
