"""Type standardization and basic cleaning of the raw data."""

import polars as pl


def standardize(data: pl.LazyFrame, time_column: str) -> pl.LazyFrame:
    """Use a single datetime precision for the time column."""
    return data.with_columns(pl.col(time_column).cast(pl.Datetime("us")))


def drop_invalid(data: pl.LazyFrame, id_column: str, time_column: str) -> pl.LazyFrame:
    """Remove rows without identifier or timestamp, and duplicated readings."""
    return (
        data.drop_nulls([id_column, time_column])
        .unique(subset=[id_column, time_column], keep="last", maintain_order=True)
    )
