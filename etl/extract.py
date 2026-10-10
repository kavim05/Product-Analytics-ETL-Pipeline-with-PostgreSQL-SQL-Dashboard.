"""STAGE 1 - EXTRACT: pull product records from the Fake Store REST API.

* HTTP session with automatic retries + exponential backoff
* Schema sanity check on the response
* Raw JSON snapshot saved to data/raw/ (audit trail / replayability)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from etl.config import settings

log = logging.getLogger("etl.extract")

EXPECTED_KEYS = {"id", "title", "price", "category"}


class ExtractionError(RuntimeError):
    """Raised when the source cannot be read or returns an unexpected shape."""


def _build_session(retries: int) -> requests.Session:
    retry = Retry(
        total=retries,
        backoff_factor=1,  # 1s, 2s, 4s ...
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


def fetch_products(
    url: str | None = None, timeout: int | None = None, retries: int | None = None
) -> list[dict]:
    """GET the product list and return the parsed JSON payload."""
    url = url or settings.api_url
    timeout = timeout or settings.api_timeout
    retries = settings.api_retries if retries is None else retries

    log.info("GET %s (timeout=%ss, retries=%s)", url, timeout, retries)
    try:
        response = _build_session(retries).get(url, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise ExtractionError(f"Failed to fetch products from {url}: {exc}") from exc

    _validate_payload(payload)
    log.info("Received %d records", len(payload))
    return payload


def _validate_payload(payload: object) -> None:
    if not isinstance(payload, list) or not payload:
        raise ExtractionError("API returned an empty or non-list payload")
    missing = EXPECTED_KEYS - set().union(*(r.keys() for r in payload if isinstance(r, dict)))
    if missing:
        raise ExtractionError(f"API payload is missing expected fields: {sorted(missing)}")


def load_sample(path: Path | None = None) -> list[dict]:
    """Offline mode: read the bundled sample file instead of calling the API."""
    path = path or settings.sample_file
    log.warning("OFFLINE MODE - reading sample data from %s", path)
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    _validate_payload(payload)
    return payload


def save_raw_snapshot(payload: list[dict], directory: Path | None = None) -> Path:
    directory = directory or settings.raw_dir
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = directory / f"products_{stamp}.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log.info("Raw snapshot saved -> %s", out)
    return out


def to_dataframe(payload: list[dict]) -> pd.DataFrame:
    """Flatten nested JSON (rating.rate / rating.count) into a flat DataFrame."""
    df = pd.json_normalize(payload)
    df = df.rename(columns={"rating.rate": "rating_rate", "rating.count": "rating_count"})
    for col in ("rating_rate", "rating_count", "description", "image"):
        if col not in df.columns:
            df[col] = None
    return df


def extract(offline: bool = False, save_snapshot: bool = True) -> pd.DataFrame:
    """Public entry point for stage 1."""
    payload = load_sample() if offline else fetch_products()
    if save_snapshot:
        save_raw_snapshot(payload)
    return to_dataframe(payload)
