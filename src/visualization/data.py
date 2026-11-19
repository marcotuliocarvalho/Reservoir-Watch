"""Loading, preparation and aggregation of the data shown in the dashboard."""

import glob
import os
import unicodedata
from dataclasses import dataclass, fields
from datetime import date, timedelta
from pathlib import Path

import polars as pl

from src.ingestion import IngestionConfig, pipeline, reader

from . import geo

STATIC = Path(__file__).parent / "static"
REGISTRY_PATH = STATIC / "reservatorios.parquet"

# Fixed orders: each area keeps the same color whatever the filter.
SUBSYSTEM_ORDER = ["Sudeste/Centro-Oeste", "Sul", "Nordeste", "Norte"]
REGION_ORDER = geo.REGION_ORDER

GROUPS = {
    "regiao": {"label": "Region", "column": "regiao", "order": REGION_ORDER},
    "subsistema": {"label": "Subsystem", "column": "subsistema", "order": SUBSYSTEM_ORDER},
}

METRICS = {
    "volume_util": {
        "label": "Useful volume",
        "short": "Useful volume",
        "description": "Stored useful volume (% of maximum useful volume)",
    },
    "nivel_norm": {
        "label": "Normalized level",
        "short": "Level",
        "description": "Upstream level divided by the reservoir's highest historical level",
    },
}

FLOW_COLUMNS = {"vazao_afluente": "Inflow", "vazao_defluente": "Outflow"}
MEASUREMENTS = ["volume_util", "nivel_norm", *FLOW_COLUMNS]

TYPE_LABELS = {
    "RCU": "Reservoir with power plant",
    "RES": "Reservoir without power plant",
    "RBB": "Reservoir with pumped-storage plant",
    "FIO": "Run-of-river",
}

# ---------- Criticality ----------
# Alerts use the useful volume of storage reservoirs only: run-of-river plants
# (FIO) have almost no storage, so their volume says little about scarcity.
STORAGE_TYPES = ["RCU", "RES", "RBB"]
CRITICAL_BELOW = 20.0  # % of useful volume
ALERT_BELOW = 40.0
FAST_DROP = 10.0  # percentage points lost in 30 days

STATUS_ORDER = ["Critical", "Alert", "Watch", "Normal", "Unclassified"]
STATUS_RULES = {
    "Critical": f"useful volume below {CRITICAL_BELOW:.0f}%",
    "Alert": f"useful volume between {CRITICAL_BELOW:.0f}% and {ALERT_BELOW:.0f}%",
    "Watch": f"drop of {FAST_DROP:.0f} pp or more in 30 days",
    "Normal": "no triggers",
    "Unclassified": "run-of-river or no volume reading",
}


def resolve_sources(source: str | Path | None = None) -> list[str]:
    """Return the Parquet files to read.

    ``source`` can be one file, a directory or a glob pattern. Without it, the
    ``HIDRIC_DATA_DIR`` environment variable is used, then ``./data``.
    """
    candidates = [source] if source else [os.getenv("HIDRIC_DATA_DIR"), "data"]

    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_dir():
            files = sorted(str(file) for file in path.glob("*.parquet"))
        elif any(char in str(candidate) for char in "*?["):
            files = sorted(glob.glob(str(candidate)))
        elif path.is_file():
            files = [str(path)]
        else:
            files = []
        if files:
            return files

    raise FileNotFoundError(
        "No Parquet file found. Pass --source or set HIDRIC_DATA_DIR."
    )


def _normalize_name(expr: pl.Expr) -> pl.Expr:
    return expr.str.to_uppercase().str.replace_all(r"[^A-Z0-9]", "")


def _ascii(text: str | None) -> str | None:
    if text is None:
        return None
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def load_registry(path: str | Path | None = None) -> pl.DataFrame | None:
    """ONS reservoir registry: coordinates, state and useful capacity.

    Source: dados.ons.org.br, dataset "reservatorio" (RESERVATORIOS.parquet).
    The state comes from the CEG code (``UHE.PH.<UF>.…``).
    """
    path = Path(path or os.getenv("HIDRIC_REGISTRY") or REGISTRY_PATH)
    if not path.is_file():
        return None

    raw = pl.read_parquet(path)
    return raw.select(
        pl.col("res_id").alias("id_reservatorio"),
        _normalize_name(
            pl.col("nom_reservatorio").map_elements(_ascii, return_dtype=pl.String)
        ).alias("nome_chave"),
        pl.col("ceg").str.extract(r"^[^.]+\.[^.]+\.([A-Z]{2})\.").alias("uf"),
        pl.col("val_latitude").alias("lat"),
        pl.col("val_longitude").alias("lon"),
        pl.col("val_volutiltot").cast(pl.Float64, strict=False).alias("capacidade_hm3"),
        pl.col("nom_rio").str.strip_chars().str.to_titlecase().alias("rio"),
    )


def attach_registry(data: pl.DataFrame, registry: pl.DataFrame | None) -> pl.DataFrame:
    """Add state, region, coordinates and capacity to each reservoir.

    Matches by reservoir id first, then by normalized name.
    """
    extra = ["uf", "lat", "lon", "capacidade_hm3", "rio"]
    if registry is None:
        return data.with_columns(
            *(pl.lit(None, dtype=pl.Float64 if c in ("lat", "lon", "capacidade_hm3") else pl.String).alias(c) for c in extra),
            pl.lit(None, dtype=pl.String).alias("regiao"),
        )

    reservoirs = data.select("id_reservatorio", "reservatorio").unique("id_reservatorio")
    by_id = reservoirs.join(registry.drop("nome_chave"), on="id_reservatorio", how="inner")

    missing = reservoirs.join(by_id.select("id_reservatorio"), on="id_reservatorio", how="anti")
    by_name = (
        missing.with_columns(
            _normalize_name(
                pl.col("reservatorio").map_elements(_ascii, return_dtype=pl.String)
            ).alias("nome_chave")
        )
        .join(
            registry.drop("id_reservatorio").unique("nome_chave", keep="none"),
            on="nome_chave", how="inner",
        )
        .drop("nome_chave")
    )

    lookup = (
        pl.concat([by_id, by_name], how="diagonal_relaxed")
        .drop("reservatorio")
        .with_columns(pl.col("uf").replace_strict(geo.UF_REGION, default=None).alias("regiao"))
    )
    return data.join(lookup, on="id_reservatorio", how="left")


def prepare(data: pl.LazyFrame) -> pl.LazyFrame:
    """Select and rename the columns used by the dashboard.

    Raw ONS files go through the ingestion pipeline first. Useful volume
    readings outside [-10, 110] are treated as sensor errors and dropped; the
    rest is clipped to [0, 100]. Rows without any measurement are dropped:
    ONS publishes placeholder rows for the current day before the readings
    arrive, and they would show the last day as empty.
    """
    if "capacity" not in data.collect_schema().names():
        data = pipeline.process(data, IngestionConfig())

    volume = pl.col("val_volumeutilcon")
    return data.select(
        pl.col("id_reservatorio"),
        pl.col("nom_reservatorio").str.strip_chars().str.to_titlecase().alias("reservatorio"),
        pl.col("nom_subsistema").str.strip_chars().alias("subsistema"),
        pl.col("nom_bacia").str.strip_chars().str.to_titlecase().alias("bacia"),
        pl.col("nom_ree").str.strip_chars().str.to_titlecase().alias("ree"),
        pl.col("tip_reservatorio").str.strip_chars().alias("tipo"),
        pl.col("din_instante").cast(pl.Date).alias("data"),
        pl.when(volume.is_between(-10, 110)).then(volume.clip(0, 100)).alias("volume_util"),
        (pl.col("normalized_val_nivelmontante") * 100).alias("nivel_norm"),
        pl.col("val_vazaoafluente").alias("vazao_afluente"),
        pl.col("val_vazaodefluente").alias("vazao_defluente"),
    ).filter(pl.any_horizontal(pl.col(c).is_not_null() for c in MEASUREMENTS))


# Columns of a dataset written by ``export_dataset``: already prepared and
# joined with the registry, so it loads without the heavy steps.
PREPARED_MARKER = {"volume_util", "regiao"}


def load_dataset(source: str | Path | None = None, registry: str | Path | None = None) -> pl.DataFrame:
    """Read, prepare and collect the dashboard dataset."""
    scan = reader.scan_parquets(resolve_sources(source))
    if PREPARED_MARKER <= set(scan.collect_schema().names()):
        return scan.collect().sort("data")
    data = prepare(scan).collect().sort("data")
    return attach_registry(data, load_registry(registry))


def export_dataset(output: str | Path, source: str | Path | None = None, registry: str | Path | None = None) -> Path:
    """Write the dashboard dataset, prepared and joined with the registry.

    Loading this file skips the pipeline and the registry join, which keeps
    the memory peak low on small servers (the online demo).
    """
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    load_dataset(source, registry).write_parquet(output)
    return output


# ---------- Filters ----------
@dataclass(frozen=True)
class Filters:
    regions: list[str] | None = None
    subsystems: list[str] | None = None
    rees: list[str] | None = None
    basins: list[str] | None = None
    types: list[str] | None = None
    reservoirs: list[str] | None = None
    start: date | None = None
    end: date | None = None
    metric: str = "volume_util"
    value_range: tuple[float, float] | None = None
    statuses: list[str] | None = None

    def replace(self, **changes) -> "Filters":
        values = {f.name: getattr(self, f.name) for f in fields(self)}
        values.update(changes)
        return Filters(**values)


def apply_filters(df: pl.DataFrame, filters: Filters) -> pl.DataFrame:
    """Return the rows that match every active filter."""
    columns = {
        "regions": "regiao", "subsystems": "subsistema", "rees": "ree",
        "basins": "bacia", "types": "tipo", "reservoirs": "id_reservatorio",
    }
    conditions = [
        pl.col(column).is_in(getattr(filters, attr))
        for attr, column in columns.items()
        if getattr(filters, attr)
    ]
    if filters.start:
        conditions.append(pl.col("data") >= filters.start)
    if filters.end:
        conditions.append(pl.col("data") <= filters.end)
    df = df.filter(*conditions) if conditions else df

    # Reservoir-level filters, on the last reading of each reservoir.
    by_range = filters.value_range and tuple(filters.value_range) != (0, 100)
    if by_range or filters.statuses:
        latest = latest_by_reservoir(df, filters.metric)
        if by_range:
            low, high = filters.value_range
            latest = latest.filter(pl.col("valor").is_between(low, high))
        if filters.statuses:
            latest = latest.filter(pl.col("status").is_in(filters.statuses))
        df = df.filter(pl.col("id_reservatorio").is_in(latest["id_reservatorio"].implode()))
    return df


def options(df: pl.DataFrame, value: str, label: str | None = None, order: list[str] | None = None) -> list[dict]:
    """Dropdown options with the unique values of a column."""
    label = label or value
    unique = df.select(*dict.fromkeys([value, label])).unique().drop_nulls().sort(label)
    rows = [{"label": row[label], "value": row[value]} for row in unique.iter_rows(named=True)]
    if order:
        rows.sort(key=lambda r: order.index(r["value"]) if r["value"] in order else len(order))
    if value == "tipo":
        for row in rows:
            row["label"] = f"{row['value']} · {TYPE_LABELS[row['value']]}" if row["value"] in TYPE_LABELS else row["value"]
    return rows


# ---------- Aggregations ----------
def daily_by_group(df: pl.DataFrame, metric: str, group: str) -> pl.DataFrame:
    """Simple daily mean of ``metric`` per region or subsystem."""
    column = GROUPS[group]["column"]
    return (
        df.drop_nulls([metric, column])
        .group_by("data", column)
        .agg(pl.col(metric).mean().alias("valor"))
        .rename({column: "grupo"})
        .sort("data")
    )


def daily_flows(df: pl.DataFrame) -> pl.DataFrame:
    """Daily sum of inflow and outflow (m³/s) over the selected reservoirs."""
    return df.group_by("data").agg(pl.col(c).sum() for c in FLOW_COLUMNS).sort("data")


def _status_expr() -> pl.Expr:
    volume, delta = pl.col("volume_atual"), pl.col("delta_volume_30d")
    storage = pl.col("tipo").is_in(STORAGE_TYPES)
    return (
        pl.when(~storage | volume.is_null()).then(pl.lit("Unclassified"))
        .when(volume < CRITICAL_BELOW).then(pl.lit("Critical"))
        .when(volume < ALERT_BELOW).then(pl.lit("Alert"))
        .when(delta <= -FAST_DROP).then(pl.lit("Watch"))
        .otherwise(pl.lit("Normal"))
        .alias("status")
    )


def _last_and_delta(df: pl.DataFrame, column: str, prefix: str) -> pl.DataFrame:
    """Last value of ``column`` per reservoir and its change over 30 days."""
    readings = df.select("id_reservatorio", "data", column).drop_nulls(column)
    last = readings.group_by("id_reservatorio").agg(
        pl.col("data").max().alias(f"data_{prefix}"),
        pl.col(column).sort_by("data").last().alias(f"{prefix}_atual"),
    )
    reference = (
        readings.join(last, on="id_reservatorio")
        .filter(pl.col("data") <= pl.col(f"data_{prefix}") - pl.duration(days=30))
        .group_by("id_reservatorio")
        .agg(pl.col(column).sort_by("data").last().alias("_ref"))
    )
    return (
        last.join(reference, on="id_reservatorio", how="left")
        .with_columns((pl.col(f"{prefix}_atual") - pl.col("_ref")).alias(f"delta_{prefix}_30d"))
        .drop("_ref")
    )


def latest_by_reservoir(df: pl.DataFrame, metric: str) -> pl.DataFrame:
    """Last reading of each reservoir with its status, sorted by ``valor``.

    ``valor`` and ``delta_30d`` refer to ``metric``; the status always uses
    the useful volume.
    """
    if df.is_empty():
        return pl.DataFrame(schema={"id_reservatorio": pl.String, "valor": pl.Float64, "status": pl.String})

    info_columns = [
        "id_reservatorio", "reservatorio", "subsistema", "regiao", "uf", "ree", "bacia", "rio",
        "tipo", "lat", "lon", "capacidade_hm3", "data", "vazao_afluente", "vazao_defluente",
    ]
    info = df.sort("data").group_by("id_reservatorio").last().select(info_columns)
    volume = _last_and_delta(df, "volume_util", "volume")

    result = info.join(volume.drop("data_volume"), on="id_reservatorio", how="left")
    if metric == "volume_util":
        result = result.with_columns(
            pl.col("volume_atual").alias("valor"), pl.col("delta_volume_30d").alias("delta_30d"),
        )
    else:
        chosen = _last_and_delta(df, metric, "metric").drop("data_metric")
        result = result.join(chosen, on="id_reservatorio", how="left").rename(
            {"metric_atual": "valor", "delta_metric_30d": "delta_30d"}
        )
    return result.with_columns(_status_expr()).drop_nulls("valor").sort("valor")


def alerts(latest: pl.DataFrame) -> pl.DataFrame:
    """Reservoirs that hit a criticality trigger, most severe first."""
    if latest.is_empty():
        return latest
    rank = {status: i for i, status in enumerate(STATUS_ORDER)}
    return (
        latest.filter(pl.col("status").is_in(["Critical", "Alert", "Watch"]))
        .with_columns(pl.col("status").replace_strict(rank, return_dtype=pl.Int8).alias("_rank"))
        .sort("_rank", "volume_atual")
        .drop("_rank")
    )


def group_summary(latest: pl.DataFrame, group: str) -> pl.DataFrame:
    """Per region or subsystem: means, capacity-weighted volume and alert counts."""
    column = GROUPS[group]["column"]
    if latest.is_empty():
        return pl.DataFrame(schema={"grupo": pl.String})
    weight = pl.col("capacidade_hm3").fill_null(0)
    storage = latest.filter(pl.col("tipo").is_in(STORAGE_TYPES))
    weighted = (
        storage.drop_nulls(["volume_atual", "capacidade_hm3"])
        .group_by(column)
        .agg(
            ((pl.col("volume_atual") * weight).sum() / weight.sum()).alias("volume_ponderado"),
            weight.sum().alias("capacidade_hm3"),
        )
    )
    return (
        latest.drop_nulls(column)
        .group_by(column)
        .agg(
            pl.col("valor").mean().alias("valor"),
            pl.col("delta_30d").mean().alias("delta_30d"),
            pl.len().alias("reservatorios"),
            (pl.col("status") == "Critical").sum().alias("criticos"),
            (pl.col("status") == "Alert").sum().alias("alertas"),
            (pl.col("status") == "Watch").sum().alias("atencao"),
        )
        .join(weighted, on=column, how="left")
        .rename({column: "grupo"})
    )


def reservoir_history(df: pl.DataFrame, reservoir_id: str) -> pl.DataFrame:
    """All readings of one reservoir, oldest first."""
    return df.filter(pl.col("id_reservatorio") == reservoir_id).sort("data")


@dataclass(frozen=True)
class Summary:
    last_date: date | None
    metric_value: float | None
    metric_delta: float | None
    inflow: float | None
    outflow: float | None
    reservoirs: int


def summarize(df: pl.DataFrame, metric: str, window_days: int = 30) -> Summary:
    """Headline numbers for the last day of the filtered data.

    ``metric_delta`` compares the last day with ``window_days`` before, in
    percentage points.
    """
    if df.is_empty():
        return Summary(None, None, None, None, None, 0)

    last_date = df["data"].max()
    last = df.filter(pl.col("data") == last_date)
    metric_value = last[metric].mean()

    previous = df.filter(pl.col("data") == last_date - timedelta(days=window_days))
    previous_value = previous[metric].mean() if not previous.is_empty() else None
    delta = (
        metric_value - previous_value
        if metric_value is not None and previous_value is not None
        else None
    )

    return Summary(
        last_date=last_date,
        metric_value=metric_value,
        metric_delta=delta,
        inflow=last["vazao_afluente"].sum(),
        outflow=last["vazao_defluente"].sum(),
        reservoirs=last["id_reservatorio"].n_unique(),
    )
