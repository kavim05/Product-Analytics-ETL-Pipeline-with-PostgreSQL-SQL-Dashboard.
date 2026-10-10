import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from etl.extract import to_dataframe  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample" / "products_sample.json"


@pytest.fixture
def sample_payload():
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


@pytest.fixture
def raw_df(sample_payload):
    return to_dataframe(sample_payload)


@pytest.fixture
def dirty_df():
    return pd.DataFrame([
        {"id": 100, "title": "  Good   product ", "price": "19.99", "category": "  Electronics ",
         "rating_rate": 4.5, "rating_count": 10, "description": "ok", "image": "x"},
        {"id": 101, "title": "Negative price", "price": -5, "category": "x",
         "rating_rate": 3, "rating_count": 1, "description": "d", "image": "x"},
        {"id": 102, "title": "", "price": "abc", "category": None,
         "rating_rate": 9, "rating_count": -1, "description": "d", "image": "x"},
        {"id": 103, "title": "Dup old", "price": 10, "category": "x",
         "rating_rate": 3, "rating_count": 1, "description": "d", "image": "x"},
        {"id": 103, "title": "Dup new", "price": 11, "category": "x",
         "rating_rate": 3, "rating_count": 1, "description": "d", "image": "x"},
    ])


@pytest.fixture
def sqlite_engine(tmp_path):
    from etl import load
    engine = load.get_engine(f"sqlite:///{tmp_path/'test.db'}")
    load.init_db(engine)
    return engine
