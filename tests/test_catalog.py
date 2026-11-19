import pytest

from src.ingestion import catalog
from src.ingestion.config import IngestionConfig

BASE = "https://example.org/dataset/DADOS_HIDROLOGICOS_RES_{}.parquet"


def _resource(url: str, fmt: str = "PARQUET") -> dict:
    return {"url": url, "format": fmt}


@pytest.fixture
def resources(monkeypatch):
    items = [
        _resource(BASE.format(2024)),
        _resource(BASE.format(2022)),
        _resource(BASE.format(2023).replace(".parquet", ".csv"), fmt="CSV"),
        _resource("https://example.org/dataset/DICIONARIO.parquet"),
        _resource(BASE.format(2023), fmt="parquet"),
    ]
    monkeypatch.setattr(catalog, "fetch_resources", lambda config: items)
    return items


def test_returns_parquet_urls_sorted_by_year(resources):
    urls = catalog.get_parquet_urls(IngestionConfig())
    assert urls == [BASE.format(2022), BASE.format(2023), BASE.format(2024)]


def test_filters_by_years(resources):
    urls = catalog.get_parquet_urls(IngestionConfig(years=(2024, 2030)))
    assert urls == [BASE.format(2024)]


@pytest.mark.parametrize(
    ("url", "year"),
    [
        ("https://x/DADOS_HIDROLOGICOS_RES_2025.parquet", 2025),
        ("https://x/RESERVATORIOS.parquet", None),
        ("https://x/DADOS_RES_ATUAL.parquet", None),
    ],
)
def test_year_from_url(url, year):
    assert catalog._year_from_url(url) == year


def test_fetch_resources_calls_ckan_api(monkeypatch):
    calls = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"result": {"resources": [{"url": "a"}]}}

    def fake_get(url, params, timeout):
        calls.update(url=url, params=params, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr(catalog.requests, "get", fake_get)
    config = IngestionConfig(api_url="https://ckan/api", dataset_id="ds", timeout=5)

    assert catalog.fetch_resources(config) == [{"url": "a"}]
    assert calls == {"url": "https://ckan/api", "params": {"id": "ds"}, "timeout": 5}
