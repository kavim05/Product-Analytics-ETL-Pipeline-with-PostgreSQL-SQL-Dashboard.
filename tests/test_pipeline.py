import pytest

import main
from etl import analytics


def test_end_to_end_offline_sqlite(tmp_path, monkeypatch):
    """Full pipeline on bundled sample data, writing charts/reports to tmp."""
    from etl import extract
    monkeypatch.setattr(extract, "save_raw_snapshot", lambda p: None)
    monkeypatch.setattr(analytics, "export_reports", lambda r: None)
    monkeypatch.setattr(analytics, "make_charts", lambda r: [])
    out = main.run_pipeline(offline=True, db_url=f"sqlite:///{tmp_path/'e2e.db'}")
    assert out["status"] == "SUCCESS" and out["rows_loaded"] == 20


def test_sql_queries_all_parse_and_run(sqlite_engine, raw_df):
    from etl import load, transform
    res = transform.transform(raw_df)
    load.load(sqlite_engine, raw_df, res.clean, res.rejected)
    results = analytics.run_queries(sqlite_engine)
    assert len(results) == 10
    assert results["kpi_overview"].iloc[0]["total_products"] == 20


def test_pipeline_failure_is_recorded(tmp_path, monkeypatch):
    from etl import extract
    def boom(*a, **k): raise extract.ExtractionError("API down")
    monkeypatch.setattr(extract, "fetch_products", boom)
    db = f"sqlite:///{tmp_path/'fail.db'}"
    with pytest.raises(extract.ExtractionError):
        main.run_pipeline(offline=False, db_url=db)
    from etl import load
    from sqlalchemy import select
    with load.get_engine(db).connect() as c:
        assert c.execute(select(load.pipeline_runs.c.status)).scalar_one() == "FAILED"
