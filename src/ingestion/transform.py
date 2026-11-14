"""Feature engineering over the hydrological data."""

import polars as pl


def normalize_by_max(data: pl.LazyFrame, id_column: str, target_column: str) -> pl.LazyFrame:
    """Divide ``target_column`` by its historical maximum per ``id_column``.

    The maximum is an estimate of the reservoir capacity. The result goes to
    ``normalized_<target_column>``.
    """
    capacity = pl.col(target_column).max().over(id_column)
    return data.with_columns(
        capacity.alias("capacity"),
        (pl.col(target_column) / capacity).alias(f"normalized_{target_column}"),
    )
