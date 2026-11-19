from datetime import datetime

import polars as pl

from src.ingestion import cleaning, transform


def test_standardize_casts_time_to_microseconds():
    data = pl.LazyFrame({"t": [datetime(2025, 1, 1)]}).with_columns(pl.col("t").cast(pl.Datetime("ns")))
    result = cleaning.standardize(data, "t").collect()
    assert result.schema["t"] == pl.Datetime("us")


def test_drop_invalid_removes_nulls_and_keeps_last_duplicate():
    data = pl.LazyFrame({
        "id": ["A", "A", "A", None, "B"],
        "t": [1, 1, 2, 3, None],
        "v": [10, 11, 12, 13, 14],
    })
    result = cleaning.drop_invalid(data, "id", "t").collect()
    assert result.to_dicts() == [{"id": "A", "t": 1, "v": 11}, {"id": "A", "t": 2, "v": 12}]


def test_normalize_by_max_is_per_reservoir():
    data = pl.LazyFrame({"id": ["A", "A", "B", "B"], "level": [50.0, 100.0, 10.0, 40.0]})
    result = transform.normalize_by_max(data, "id", "level").collect()
    assert result["capacity"].to_list() == [100.0, 100.0, 40.0, 40.0]
    assert result["normalized_level"].to_list() == [0.5, 1.0, 0.25, 1.0]
