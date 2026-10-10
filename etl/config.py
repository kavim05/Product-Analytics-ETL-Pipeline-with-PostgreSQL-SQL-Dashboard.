"""Central configuration. Values come from environment variables / a .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    api_url: str = os.getenv("API_URL", "https://fakestoreapi.com/products")
    api_timeout: int = int(os.getenv("API_TIMEOUT", "15"))
    api_retries: int = int(os.getenv("API_RETRIES", "3"))
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://etl_user:etl_pass@localhost:5432/ecommerce_db",
    )
    raw_dir: Path = ROOT / "data" / "raw"
    sample_file: Path = ROOT / "data" / "sample" / "products_sample.json"
    sql_dir: Path = ROOT / "sql"
    reports_dir: Path = ROOT / "reports"
    charts_dir: Path = ROOT / "docs" / "charts"
    log_dir: Path = ROOT / "logs"


settings = Settings()
