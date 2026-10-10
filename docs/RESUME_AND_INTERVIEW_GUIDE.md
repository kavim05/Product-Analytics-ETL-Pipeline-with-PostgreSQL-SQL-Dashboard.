# Resume & Interview Guide (not for GitHub README – keep for yourself)

## Resume project entry (copy/paste)

**E-commerce ETL Pipeline** | Python, pandas, SQLAlchemy, PostgreSQL, REST API, Docker, pytest | [GitHub link]
- Built a modular ETL pipeline (extract / transform / load / analytics) that ingests product data from a REST API into PostgreSQL, orchestrated through a single CLI entry point with per-stage timing and error handling.
- Implemented idempotent loads using `INSERT … ON CONFLICT` upserts inside atomic transactions, with a staging table for reconciliation.
- Designed a data-quality layer with validation rules and a quarantine table that records every rejected row with its reason; added feature engineering (price tiers, popularity score).
- Wrote 10 analytical SQL queries (window functions, views, joins) and auto-generated a 6-chart KPI dashboard with matplotlib.
- Added observability (rotating logs, `pipeline_runs` audit table), 20 pytest tests, Docker Compose for the DB, and GitHub Actions CI running tests against PostgreSQL.

(Only add numbers you can defend – e.g. "20 automated tests", "10 SQL queries", "4 tables + 2 views". Don't claim scale you haven't run.)

## Likely interview questions & short answers

1. **What makes your pipeline idempotent?** Upsert on primary key (`ON CONFLICT DO UPDATE`); staging table is replaced each run. I verified that running it 3x leaves the row count unchanged (see `test_load_is_idempotent`).
2. **What if the API is down?** Retries with exponential backoff; if still failing it raises `ExtractionError`, the run is marked `FAILED` in `pipeline_runs` with the message, and nothing is loaded (see `test_pipeline_failure_is_recorded`).
3. **How do you handle bad data?** Validation rules produce a reason per row; bad rows go to `rejected_products` instead of being dropped.
4. **Why a transaction?** So staging and main tables never get out of sync if a load fails midway.
5. **How would you scale this?** Incremental extraction by `updated_at`, batch `COPY` instead of row inserts, partitioning, orchestrate with Airflow, run in containers on cloud.
6. **ETL vs ELT?** This is ETL (transform in pandas before load). With larger data/warehouse I'd land raw first and transform in SQL (dbt) = ELT.
7. **A bug I hit while building it** (good story!): `ROUND(double precision, int)` works in SQLite but not PostgreSQL – I caught it by testing on real Postgres, not just the test DB, and fixed it with an explicit `CAST(… AS NUMERIC)`.

## LinkedIn / GitHub tips
- Pin the repo; add topics: `etl`, `data-engineering`, `python`, `postgresql`, `pandas`, `sqlalchemy`.
- Replace `<your-username>` in README badges.
- Run `python main.py` once with internet so charts reflect live API data, then commit.
