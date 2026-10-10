import pytest
import requests

from etl import extract


def test_to_dataframe_flattens_rating(sample_payload):
    df = extract.to_dataframe(sample_payload)
    assert {"rating_rate", "rating_count"} <= set(df.columns)
    assert len(df) == 20


def test_load_sample_offline():
    assert len(extract.load_sample()) == 20


def test_fetch_products_ok(monkeypatch, sample_payload):
    class Resp:
        def raise_for_status(self): pass
        def json(self): return sample_payload
    monkeypatch.setattr(requests.Session, "get", lambda *a, **k: Resp())
    assert len(extract.fetch_products("https://example.test/products")) == 20


def test_fetch_products_http_error(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("down")
    monkeypatch.setattr(requests.Session, "get", boom)
    with pytest.raises(extract.ExtractionError):
        extract.fetch_products("https://example.test/products", retries=0)


@pytest.mark.parametrize("payload", [[], {}, [{"id": 1}]])
def test_invalid_payload_rejected(payload):
    with pytest.raises(extract.ExtractionError):
        extract._validate_payload(payload)
