"""Ingestion pipeline: discover, read, clean and transform.

The plain functions (``process``, ``load_raw``, ``run_ingestion``...) work
without Airflow. ``build_dag`` wraps the same steps in an Airflow DAG; the
Airflow import happens inside it, so the dashboard and the CLI do not need
Airflow installed.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

import polars as pl

from . import catalog, cleaning, reader, transform
from .config import IngestionConfig

DAG_ID = "hidrico_ingestion"
OUTPUT_NAME = "reservatorios_hidrologicos.parquet"


# ---------- Plain pipeline ----------
def process(data: pl.LazyFrame, config: IngestionConfig) -> pl.LazyFrame:
    """Clean and transform the raw data."""
    data = cleaning.standardize(data, config.time_column)
    data = cleaning.drop_invalid(data, config.id_column, config.time_column)
    return transform.normalize_by_max(data, config.id_column, config.target_column)


def load_raw(config: IngestionConfig) -> pl.LazyFrame:
    """Return the raw data of all available years as a LazyFrame."""
    urls = catalog.get_parquet_urls(config)
    return reader.scan_parquets(urls)


def process_files(paths: list[str | Path], config: IngestionConfig) -> pl.LazyFrame:
    """Clean and transform Parquet files that are already on disk."""
    return process(reader.scan_parquets(paths), config)


def run_ingestion(config: IngestionConfig | None = None) -> pl.LazyFrame:
    """Run the full ingestion and return the processed LazyFrame."""
    config = config or IngestionConfig.from_env()
    return process(load_raw(config), config)


# ---------- File-based steps (used by the DAG) ----------
def data_dir() -> Path:
    """Root data directory: ``HIDRIC_DATA_DIR`` or ``./data``."""
    return Path(os.getenv("HIDRIC_DATA_DIR", "data"))


def _year_of(path: Path) -> int | None:
    suffix = path.stem.rsplit("_", 1)[-1]
    return int(suffix) if suffix.isdigit() else None


def fetch_year(url: str, raw_dir: str | Path, timeout: int = 30) -> Path:
    """Download one yearly file, skipping closed years already on disk.

    The current year is always downloaded again, because ONS keeps adding
    readings to it.
    """
    target = Path(raw_dir) / os.path.basename(url)
    year = _year_of(target)
    if target.is_file() and year is not None and year < date.today().year:
        return target
    return reader.download_parquet(url, raw_dir, timeout=timeout)


def write_processed(paths: list[str | Path], output: str | Path, config: IngestionConfig) -> Path:
    """Process local raw files and write one Parquet file atomically."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_suffix(".part")
    process_files(paths, config).collect().write_parquet(partial)
    partial.replace(output)
    return output


def ingest_to_disk(config: IngestionConfig, root: str | Path | None = None, workers: int = 4) -> Path:
    """Download every yearly file and write the processed dataset.

    Same result as one DAG run, without Airflow: ``workers`` parallel
    downloads, like the DAG's ``max_active_tis_per_dag``. Used by the CLI and
    the online demo image.
    """
    root = Path(root) if root is not None else data_dir()
    urls = catalog.get_parquet_urls(config)
    if not urls:
        raise ValueError("Nenhum arquivo Parquet encontrado no catálogo da ONS.")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        paths = list(pool.map(lambda url: fetch_year(url, root / "raw", timeout=config.timeout), urls))
    return write_processed(paths, root / OUTPUT_NAME, config)


# ---------- Airflow DAG ----------
def build_dag():
    """Build the Airflow DAG: discover -> download (one task per year) -> process.

    Tasks exchange file paths, never DataFrames: XCom only stores small
    JSON values.
    """
    from airflow.sdk import Param, dag, get_current_context, task

    @dag(
        dag_id=DAG_ID,
        schedule="@daily",
        start_date=datetime(2026, 1, 1),
        catchup=False,
        max_active_runs=1,
        default_args={"retries": 2},
        params={
            "years": Param(
                [],
                type="array",
                description="Anos a ingerir. Lista vazia = todos os anos disponíveis.",
            ),
        },
        tags=["hidrico", "ingestion"],
        doc_md=__doc__,
    )
    def hidrico_ingestion():
        @task
        def discover() -> list[str]:
            years = get_current_context()["params"].get("years") or None
            config = IngestionConfig.from_env(years=tuple(years) if years else None)
            urls = catalog.get_parquet_urls(config)
            if not urls:
                raise ValueError("Nenhum arquivo Parquet encontrado no catálogo da ONS.")
            return urls

        @task(max_active_tis_per_dag=4)
        def download(url: str) -> str:
            config = IngestionConfig.from_env()
            return str(fetch_year(url, data_dir() / "raw", timeout=config.timeout))

        @task
        def transform_and_save(downloaded: list[str]) -> str:
            # Use every raw year on disk, not only the ones refreshed in this
            # run, so a run with "years" set does not shrink the output.
            paths = sorted({*downloaded, *map(str, (data_dir() / "raw").glob("*.parquet"))})
            # The dashboard reads every *.parquet in the data dir root.
            output = data_dir() / OUTPUT_NAME
            return str(write_processed(paths, output, IngestionConfig.from_env()))

        transform_and_save(download.expand(url=discover()))

    return hidrico_ingestion()
