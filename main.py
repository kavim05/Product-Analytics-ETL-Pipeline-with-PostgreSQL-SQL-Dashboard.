"""ORCHESTRATION LAYER - runs Extract -> Transform -> Load -> Analytics in sequence.

Usage
-----
    python main.py                     # live API  -> PostgreSQL (DATABASE_URL)
    python main.py --offline           # bundled sample data (no internet needed)
    python main.py --db-url sqlite:///demo.db --offline
    python main.py --no-analytics      # skip charts / CSV reports
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from contextlib import contextmanager

from etl import analytics, extract, load, transform
from etl.config import settings
from etl.logger import setup_logging

log = logging.getLogger("etl.main")


@contextmanager
def stage(name: str):
    """Time a pipeline stage and log failures with context."""
    start = time.perf_counter()
    log.info("▶ %s started", name)
    try:
        yield
    except Exception:
        log.exception("✖ %s FAILED after %.2fs", name, time.perf_counter() - start)
        raise
    log.info("✔ %s finished in %.2fs", name, time.perf_counter() - start)


def run_pipeline(offline: bool = False, db_url: str | None = None,
                 run_analytics: bool = True) -> dict:
    engine = load.get_engine(db_url)
    load.init_db(engine)
    run_id = load.start_run(engine)
    log.info("Pipeline run #%d started", run_id)
    counts: dict = {}
    try:
        with stage("EXTRACT"):
            raw = extract.extract(offline=offline)
            counts["rows_extracted"] = len(raw)

        with stage("TRANSFORM"):
            result = transform.transform(raw)
            counts["rows_rejected"] = result.stats["rows_rejected"]

        with stage("LOAD"):
            summary = load.load(engine, raw, result.clean, result.rejected, run_id)
            counts["rows_loaded"] = summary["upserted"]

        if run_analytics:
            with stage("ANALYTICS"):
                results = analytics.run_queries(engine)
                analytics.export_reports(results)
                analytics.make_charts(results)

        load.finish_run(engine, run_id, "SUCCESS", **counts)
        log.info("Pipeline run #%d SUCCESS %s", run_id, counts)
        return {"run_id": run_id, "status": "SUCCESS", **counts}
    except Exception as exc:
        load.finish_run(engine, run_id, "FAILED", error_message=str(exc)[:1000], **counts)
        log.error("Pipeline run #%d FAILED: %s", run_id, exc)
        raise


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="E-commerce ETL pipeline")
    p.add_argument("--offline", action="store_true", help="use bundled sample data instead of the API")
    p.add_argument("--db-url", default=None, help=f"SQLAlchemy URL (default: DATABASE_URL / {settings.database_url.split('@')[-1]})")
    p.add_argument("--no-analytics", action="store_true", help="skip SQL analytics + charts")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    setup_logging(args.log_level)
    try:
        run_pipeline(args.offline, args.db_url, not args.no_analytics)
    except Exception as exc:
        log.error("Pipeline aborted: %s", exc, exc_info=args.log_level == "DEBUG")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
