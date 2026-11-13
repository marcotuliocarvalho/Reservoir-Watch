"""Discovery of the Parquet resources published in the ONS CKAN catalog."""

import os

import requests

from .config import IngestionConfig


def fetch_resources(config: IngestionConfig) -> list[dict]:
    """Return the raw resource list of the dataset from the CKAN API."""
    response = requests.get(
        config.api_url,
        params={"id": config.dataset_id},
        timeout=config.timeout,
    )
    response.raise_for_status()
    return response.json()["result"]["resources"]


def _is_parquet(resource: dict) -> bool:
    url = resource.get("url", "")
    return resource.get("format", "").upper() == "PARQUET" and url.endswith(".parquet")


def _year_from_url(url: str) -> int | None:
    """Extract the year from names like DADOS_HIDROLOGICOS_RES_2025.parquet."""
    suffix = os.path.basename(url).removesuffix(".parquet").rsplit("_", 1)[-1]
    return int(suffix) if suffix.isdigit() else None


def get_parquet_urls(config: IngestionConfig) -> list[str]:
    """Return one Parquet URL per year, sorted by year.

    When ``config.years`` is set, only those years are returned.
    """
    urls_by_year: dict[int, str] = {}

    for resource in fetch_resources(config):
        if not _is_parquet(resource):
            continue
        year = _year_from_url(resource["url"])
        if year is None:
            continue
        if config.years is not None and year not in config.years:
            continue
        urls_by_year[year] = resource["url"]

    return [urls_by_year[year] for year in sorted(urls_by_year)]
