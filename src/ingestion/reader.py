"""Download and lazy reading of the Parquet files."""

import os
from pathlib import Path

import polars as pl
import requests


def download_parquet(url: str, dest_dir: str | Path, timeout: int = 30) -> Path:
    """Download one Parquet file to ``dest_dir`` and return its local path.

    The file goes to a temporary name first, so a failed download never
    leaves a partial file with the final name.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / os.path.basename(url)
    partial = target.with_suffix(".part")

    with requests.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        with partial.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1 << 20):
                file.write(chunk)

    partial.replace(target)
    return target


def scan_parquets(sources: list[str | Path]) -> pl.LazyFrame:
    """Scan every Parquet source (URL or local path) and concatenate them.

    ``diagonal_relaxed`` tolerates small schema differences between years
    (for example, different datetime precisions).
    """
    if not sources:
        raise ValueError("Nenhum arquivo Parquet encontrado.")

    scans = [pl.scan_parquet(source) for source in sources]
    return pl.concat(scans, how="diagonal_relaxed")
