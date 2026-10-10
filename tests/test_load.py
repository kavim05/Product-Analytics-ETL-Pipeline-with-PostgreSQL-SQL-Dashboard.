from sqlalchemy import func, select

from etl import load
from etl.transform import transform


def _count(engine, table):
    with engine.connect() as c:
        return c.execute(select(func.count()).select_from(table)).scalar_one()


def test_load_inserts_all_tables(sqlite_engine, raw_df, dirty_df):
    res = transform(raw_df)
    out = load.load(sqlite_engine, raw_df, res.clean, transform(dirty_df).rejected, run_id=1)
    assert out["upserted"] == 20 and out["raw_loaded"] == 20
    assert _count(sqlite_engine, load.transformed_products) == 20
    assert _count(sqlite_engine, load.rejected_products) == out["rejected_logged"] > 0


def test_load_is_idempotent(sqlite_engine, raw_df):
    res = transform(raw_df)
    for _ in range(3):
        load.load(sqlite_engine, raw_df, res.clean, res.rejected)
    assert _count(sqlite_engine, load.transformed_products) == 20   # no duplicates
    assert _count(sqlite_engine, load.raw_products) == 20           # staging replaced


def test_upsert_updates_changed_rows(sqlite_engine, raw_df):
    res = transform(raw_df)
    load.load(sqlite_engine, raw_df, res.clean, res.rejected)
    changed = res.clean.copy()
    changed.loc[changed.id == 1, "price"] = 1.0
    load.load(sqlite_engine, raw_df, changed, res.rejected)
    with sqlite_engine.connect() as c:
        price = c.execute(select(load.transformed_products.c.price).where(load.transformed_products.c.id == 1)).scalar_one()
    assert float(price) == 1.0


def test_run_audit(sqlite_engine):
    run_id = load.start_run(sqlite_engine)
    load.finish_run(sqlite_engine, run_id, "SUCCESS", rows_loaded=5)
    with sqlite_engine.connect() as c:
        row = c.execute(select(load.pipeline_runs)).first()
    assert row.status == "SUCCESS" and row.rows_loaded == 5
