"""STAGE 3 - LOAD: persist data to PostgreSQL with SQLAlchemy.

Pattern
-------
raw_products          -> staging snapshot, truncated + reloaded every run (temporary)
transformed_products  -> main analytics table, UPSERTed on primary key (idempotent)
rejected_products     -> quarantined rows + reason (data-quality audit)
pipeline_runs         -> one row per execution (observability)

raw + main are written inside ONE transaction: either both succeed or neither does.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float, Integer, MetaData, Numeric,
    String, Table, Text, create_engine, func, insert, select, text, update,
)
from sqlalchemy.engine import Engine

from etl.config import settings

log = logging.getLogger("etl.load")

metadata = MetaData()

raw_products = Table(
    "raw_products", metadata,
    Column("id", Text), Column("title", Text), Column("price", Text),
    Column("description", Text), Column("category", Text), Column("image", Text),
    Column("rating_rate", Text), Column("rating_count", Text),
    Column("extracted_at", DateTime(timezone=True), nullable=False),
)

transformed_products = Table(
    "transformed_products", metadata,
    Column("id", Integer, primary_key=True, autoincrement=False),
    Column("title", Text, nullable=False),
    Column("category", String(64), nullable=False, index=True),
    Column("price", Numeric(10, 2), nullable=False),
    Column("price_tier", String(16), nullable=False),
    Column("description", Text),
    Column("description_length", Integer),
    Column("image_url", Text),
    Column("rating_rate", Float),
    Column("rating_count", Integer),
    Column("popularity_score", Float),
    Column("is_highly_rated", Boolean),
    Column("loaded_at", DateTime(timezone=True), nullable=False),
)

rejected_products = Table(
    "rejected_products", metadata,
    Column("rejected_id", BigInteger().with_variant(Integer, "sqlite"),
           primary_key=True, autoincrement=True),
    Column("run_id", Integer, index=True),
    Column("record_id", Text),
    Column("reason", Text, nullable=False),
    Column("payload", Text),
    Column("rejected_at", DateTime(timezone=True), nullable=False),
)

pipeline_runs = Table(
    "pipeline_runs", metadata,
    Column("run_id", Integer, primary_key=True, autoincrement=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True)),
    Column("status", String(16), nullable=False),
    Column("rows_extracted", Integer),
    Column("rows_loaded", Integer),
    Column("rows_rejected", Integer),
    Column("error_message", Text),
)

VIEWS = {
    "vw_category_summary": """
        SELECT category,
               COUNT(*)                         AS products,
               ROUND(AVG(price), 2)             AS avg_price,
               ROUND(CAST(AVG(rating_rate) AS NUMERIC), 2)       AS avg_rating,
               SUM(rating_count)                AS total_reviews
        FROM transformed_products
        GROUP BY category
    """,
    "vw_price_tier_summary": """
        SELECT price_tier,
               COUNT(*)                   AS products,
               ROUND(CAST(AVG(rating_rate) AS NUMERIC), 2) AS avg_rating
        FROM transformed_products
        GROUP BY price_tier
    """,
}


def get_engine(url: str | None = None) -> Engine:
    return create_engine(url or settings.database_url, pool_pre_ping=True, future=True)


def init_db(engine: Engine) -> None:
    """Create tables + analytics views if they don't exist yet."""
    metadata.create_all(engine)
    with engine.begin() as conn:
        for name, sql in VIEWS.items():
            conn.execute(text(f"DROP VIEW IF EXISTS {name}"))
            conn.execute(text(f"CREATE VIEW {name} AS {sql}"))
    log.info("Schema ready (tables + %d views)", len(VIEWS))


# --------------------------------------------------------------------------- helpers
def _records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> list of dicts with NaN/NA converted to None (safe for SQL)."""
    obj = df.astype("object")
    obj = obj.where(df.notna(), None)
    return obj.to_dict(orient="records")


def _upsert_stmt(engine: Engine):
    if engine.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    elif engine.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as dialect_insert
    else:  # pragma: no cover
        raise NotImplementedError(f"UPSERT not implemented for {engine.dialect.name}")
    stmt = dialect_insert(transformed_products)
    update_cols = {
        c.name: stmt.excluded[c.name]
        for c in transformed_products.columns
        if c.name != "id"
    }
    return stmt.on_conflict_do_update(index_elements=["id"], set_=update_cols)


# --------------------------------------------------------------------------- run audit
def start_run(engine: Engine) -> int:
    with engine.begin() as conn:
        res = conn.execute(
            insert(pipeline_runs).values(
                started_at=datetime.now(timezone.utc), status="RUNNING"
            )
        )
        return int(res.inserted_primary_key[0])


def finish_run(engine: Engine, run_id: int, status: str, **counts) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(pipeline_runs)
            .where(pipeline_runs.c.run_id == run_id)
            .values(finished_at=datetime.now(timezone.utc), status=status, **counts)
        )


# --------------------------------------------------------------------------- main load
def load(engine: Engine, raw: pd.DataFrame, clean: pd.DataFrame,
         rejected: pd.DataFrame, run_id: int | None = None) -> dict:
    """Load all three datasets. Raw + clean share a single transaction."""
    now = datetime.now(timezone.utc)

    raw_rows = [
        {**{k: (None if v is None else str(v)) for k, v in rec.items()}, "extracted_at": now}
        for rec in _records(
            raw.reindex(columns=[c.name for c in raw_products.columns if c.name != "extracted_at"])
        )
    ]
    clean_rows = [{**rec, "loaded_at": now} for rec in _records(clean)]
    rejected_rows = [
        {
            "run_id": run_id,
            "record_id": None if rec.get("id") is None else str(rec["id"]),
            "reason": rec["reject_reason"],
            "payload": json.dumps(rec, default=str),
            "rejected_at": now,
        }
        for rec in _records(rejected)
    ]

    with engine.begin() as conn:  # <- one atomic transaction
        conn.execute(raw_products.delete())  # staging is temporary
        if raw_rows:
            conn.execute(insert(raw_products), raw_rows)
        if clean_rows:
            conn.execute(_upsert_stmt(engine), clean_rows)
        if rejected_rows:
            conn.execute(insert(rejected_products), rejected_rows)
        total = conn.execute(select(func.count()).select_from(transformed_products)).scalar_one()

    summary = {
        "raw_loaded": len(raw_rows),
        "upserted": len(clean_rows),
        "rejected_logged": len(rejected_rows),
        "table_total": int(total),
    }
    log.info("Load complete: %s", summary)
    return summary
