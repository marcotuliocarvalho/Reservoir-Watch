from datetime import datetime

import polars as pl
import pytest
import requests

from src.ingestion import reader


def test_scan_parquets_requires_sources():
    with pytest.raises(ValueError):
        reader.scan_parquets([])


def test_scan_parquets_tolerates_schema_differences(tmp_path):
    old = tmp_path / "a.parquet"
    new = tmp_path / "b.parquet"
    pl.DataFrame({"t": [datetime(2020, 1, 1)], "v": [1]}).with_columns(
        pl.col("t").cast(pl.Datetime("ns"))
    ).write_parquet(old)
    pl.DataFrame({"t": [datetime(2021, 1, 1)], "extra": ["x"]}).write_parquet(new)

    result = reader.scan_parquets([old, new]).collect()

    assert result.height == 2
    assert set(result.columns) == {"t", "v", "extra"}


class FakeResponse:
    def __init__(self, chunks, fail=False):
        self.chunks = chunks
        self.fail = fail

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.fail:
            raise requests.HTTPError("500")

    def iter_content(self, chunk_size):
        yield from self.chunks


def test_download_parquet_writes_final_file(tmp_path, monkeypatch):
    monkeypatch.setattr(reader.requests, "get", lambda *a, **k: FakeResponse([b"PAR1", b"data"]))

    target = reader.download_parquet("https://x/FILE_2024.parquet", tmp_path / "raw")

    assert target == tmp_path / "raw" / "FILE_2024.parquet"
    assert target.read_bytes() == b"PAR1data"
    assert not target.with_suffix(".part").exists()


def test_failed_download_leaves_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(reader.requests, "get", lambda *a, **k: FakeResponse([], fail=True))

    with pytest.raises(requests.HTTPError):
        reader.download_parquet("https://x/FILE_2024.parquet", tmp_path)

    assert list(tmp_path.iterdir()) == []
