from datetime import date

import polars as pl
import pytest

from src.visualization import data
from tests.conftest import LAST_DAY


def _status_by_id(latest: pl.DataFrame) -> dict:
    return dict(latest.select("id_reservatorio", "status").iter_rows())


# ---------- Sources ----------
def test_resolve_sources_from_directory_glob_and_file(tmp_path):
    for name in ("b.parquet", "a.parquet", "notes.txt"):
        (tmp_path / name).write_bytes(b"")
    expected = [str(tmp_path / "a.parquet"), str(tmp_path / "b.parquet")]

    assert data.resolve_sources(tmp_path) == expected
    assert data.resolve_sources(str(tmp_path / "*.parquet")) == expected
    assert data.resolve_sources(tmp_path / "a.parquet") == expected[:1]


def test_resolve_sources_uses_env(tmp_path, monkeypatch):
    (tmp_path / "x.parquet").write_bytes(b"")
    monkeypatch.setenv("HIDRIC_DATA_DIR", str(tmp_path))
    assert data.resolve_sources() == [str(tmp_path / "x.parquet")]


def test_resolve_sources_raises_when_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("HIDRIC_DATA_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        data.resolve_sources()


# ---------- Preparation ----------
def test_prepare_runs_pipeline_on_raw_files_and_cleans_volume(raw_frame):
    raw = raw_frame.with_columns(
        pl.when(pl.col("id_reservatorio") == "TUCURU")
        .then(pl.lit(150.0))  # sensor error
        .when(pl.col("id_reservatorio") == "FURNAS")
        .then(pl.lit(-5.0))  # slightly negative: clipped to 0
        .otherwise(pl.col("val_volumeutilcon"))
        .alias("val_volumeutilcon")
    )

    result = data.prepare(raw.lazy()).collect()

    by_id = result.group_by("id_reservatorio").agg(pl.col("volume_util").first())
    volumes = dict(by_id.iter_rows())
    assert volumes["TUCURU"] is None
    assert volumes["FURNAS"] == 0.0
    assert result["reservatorio"].unique().sort().to_list()[0] == "Furnas"
    assert result.schema["data"] == pl.Date
    assert result["nivel_norm"].max() == pytest.approx(100.0)


def test_prepare_drops_rows_without_measurements(raw_frame):
    # ONS publishes the current day with ids and timestamps but no readings.
    last_day = raw_frame.filter(pl.col("din_instante") == pl.col("din_instante").max())
    placeholder = last_day.with_columns(
        pl.col("din_instante") + pl.duration(days=1),
        *(pl.lit(None, dtype=pl.Float64).alias(c) for c in (
            "val_nivelmontante", "val_volumeutilcon", "val_vazaoafluente", "val_vazaodefluente",
        )),
    )

    result = data.prepare(pl.concat([raw_frame, placeholder], how="vertical_relaxed").lazy()).collect()

    assert result.height == raw_frame.height
    assert result["data"].max() == LAST_DAY
    assert data.summarize(result, "volume_util").inflow == 5000.0


def test_attach_registry_matches_by_id_then_name(dashboard_df):
    info = dashboard_df.unique("id_reservatorio").select("id_reservatorio", "uf", "regiao", "rio", "capacidade_hm3")
    rows = {row["id_reservatorio"]: row for row in info.iter_rows(named=True)}

    assert rows["FURNAS"]["uf"] == "MG"
    assert rows["FURNAS"]["regiao"] == "Sudeste"
    assert rows["FURNAS"]["rio"] == "Grande"
    assert rows["SERRA"]["uf"] == "GO"  # matched by name, the ids differ
    assert rows["TUCURU"]["uf"] == "PA"  # name match ignores accents
    assert rows["SOBRAD"]["capacidade_hm3"] == 28669.0


def test_attach_registry_without_registry_adds_empty_columns(raw_frame):
    df = data.prepare(raw_frame.lazy()).collect()
    result = data.attach_registry(df, None)
    assert result["uf"].null_count() == result.height
    assert result.schema["lat"] == pl.Float64


def test_load_registry_missing_file(tmp_path, monkeypatch):
    monkeypatch.delenv("HIDRIC_REGISTRY", raising=False)
    assert data.load_registry(tmp_path / "missing.parquet") is None


# ---------- Status and aggregations ----------
def test_latest_by_reservoir_classifies_status(dashboard_df):
    latest = data.latest_by_reservoir(dashboard_df, "volume_util")

    assert _status_by_id(latest) == {
        "FURNAS": "Critical",
        "SOBRAD": "Watch",
        "SERRA": "Alert",
        "TUCURU": "Normal",
    }  # ITAIPU has no volume reading, so no "valor": dropped
    assert latest["valor"].is_sorted()
    sobradinho = latest.filter(pl.col("id_reservatorio") == "SOBRAD").row(0, named=True)
    assert sobradinho["delta_30d"] == pytest.approx(-15.0)


def test_latest_by_level_keeps_unclassified_run_of_river(dashboard_df):
    latest = data.latest_by_reservoir(dashboard_df, "nivel_norm")
    assert _status_by_id(latest)["ITAIPU"] == "Unclassified"
    assert latest["valor"].max() == pytest.approx(100.0)


def test_latest_by_reservoir_empty():
    result = data.latest_by_reservoir(pl.DataFrame(), "volume_util")
    assert result.is_empty()
    assert "status" in result.columns


def test_alerts_most_severe_first(dashboard_df):
    latest = data.latest_by_reservoir(dashboard_df, "volume_util")
    assert data.alerts(latest)["id_reservatorio"].to_list() == ["FURNAS", "SERRA", "SOBRAD"]


def test_group_summary_weights_volume_by_capacity(dashboard_df):
    latest = data.latest_by_reservoir(dashboard_df, "volume_util")

    summary = data.group_summary(latest, "subsistema")
    southeast = summary.filter(pl.col("grupo") == "Sudeste/Centro-Oeste").row(0, named=True)

    expected = (15.0 * 17217 + 30.0 * 43250) / (17217 + 43250)
    assert southeast["volume_ponderado"] == pytest.approx(expected)
    assert southeast["reservatorios"] == 2
    assert southeast["criticos"] == 1
    assert southeast["alertas"] == 1


def test_daily_by_group_and_flows(dashboard_df):
    daily = data.daily_by_group(dashboard_df, "volume_util", "subsistema")
    assert set(daily["grupo"]) == {"Sudeste/Centro-Oeste", "Nordeste", "Norte"}

    flows = data.daily_flows(dashboard_df)
    assert flows.height == dashboard_df["data"].n_unique()
    assert flows["vazao_afluente"][0] == 5 * 1000.0


def test_summarize(dashboard_df):
    summary = data.summarize(dashboard_df, "volume_util")

    assert summary.last_date == LAST_DAY
    assert summary.reservoirs == 5
    assert summary.metric_value == pytest.approx((15 + 50 + 30 + 90) / 4)
    assert summary.metric_delta == pytest.approx(-15 / 4)
    assert summary.inflow == 5000.0


def test_summarize_empty():
    assert data.summarize(pl.DataFrame(), "volume_util").reservoirs == 0


# ---------- Filters ----------
def test_apply_filters_by_column_and_period(dashboard_df):
    filters = data.Filters(subsystems=["Nordeste"], start=date(2025, 6, 1), end=date(2025, 6, 10))
    result = data.apply_filters(dashboard_df, filters)
    assert set(result["id_reservatorio"]) == {"SOBRAD"}
    assert result["data"].min() == date(2025, 6, 1)
    assert result["data"].max() == date(2025, 6, 10)


def test_apply_filters_by_status_and_range(dashboard_df):
    by_status = data.apply_filters(dashboard_df, data.Filters(statuses=["Critical", "Alert"]))
    assert set(by_status["id_reservatorio"]) == {"FURNAS", "SERRA"}

    by_range = data.apply_filters(dashboard_df, data.Filters(value_range=(40, 100)))
    assert set(by_range["id_reservatorio"]) == {"SOBRAD", "TUCURU"}

    full_range = data.apply_filters(dashboard_df, data.Filters(value_range=(0, 100)))
    assert full_range.height == dashboard_df.height


def test_filters_replace():
    filters = data.Filters(regions=["Sul"]).replace(metric="nivel_norm")
    assert filters.regions == ["Sul"]
    assert filters.metric == "nivel_norm"


def test_options_order_and_type_labels(dashboard_df):
    subsystems = data.options(dashboard_df, "subsistema", order=data.SUBSYSTEM_ORDER)
    assert [o["value"] for o in subsystems] == data.SUBSYSTEM_ORDER

    types = {o["value"]: o["label"] for o in data.options(dashboard_df, "tipo")}
    assert types["FIO"] == "FIO · Run-of-river"


def test_export_and_reload_prepared_dataset(raw_frame, registry_file, tmp_path, monkeypatch):
    source = tmp_path / "raw.parquet"
    raw_frame.write_parquet(source)
    output = data.export_dataset(tmp_path / "out" / "dashboard.parquet", source, registry_file)
    expected = data.load_dataset(source, registry_file)

    # The prepared file loads as is: no pipeline, no registry needed.
    monkeypatch.setattr(data, "prepare", lambda _: pytest.fail("prepared file processed again"))
    reloaded = data.load_dataset(output, tmp_path / "missing.parquet")

    assert reloaded.sort("id_reservatorio", "data").equals(expected.sort("id_reservatorio", "data"))
    assert reloaded["uf"].null_count() < reloaded.height


def test_storage_reservoirs_drops_run_of_river(dashboard_df):
    latest = data.latest_by_reservoir(dashboard_df, "nivel_norm")
    storage = data.storage_reservoirs(latest)

    assert "Itaipu" in latest["reservatorio"].to_list()
    assert "Itaipu" not in storage["reservatorio"].to_list()
    assert set(storage["tipo"]) <= set(data.STORAGE_TYPES)
    assert storage["valor"].is_sorted()


def test_storage_reservoirs_empty():
    assert data.storage_reservoirs(data.latest_by_reservoir(pl.DataFrame(), "volume_util")).is_empty()
