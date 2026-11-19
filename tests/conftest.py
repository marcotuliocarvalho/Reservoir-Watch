"""Shared fixtures: small synthetic frames shaped like the ONS files."""

from datetime import date, datetime, timedelta

import polars as pl
import pytest

LAST_DAY = date(2025, 6, 30)
DAYS = 61  # enough history for the 30-day deltas

# id, name, subsystem, type, volume on the first day, volume on the last day
RESERVOIRS = [
    ("FURNAS", "FURNAS", "Sudeste/Centro-Oeste", "RCU", 15.0, 15.0),  # Critical
    ("SOBRAD", "SOBRADINHO", "Nordeste", "RES", 80.0, 50.0),  # Watch (fast drop)
    ("SERRA", "SERRA DA MESA", "Sudeste/Centro-Oeste", "RCU", 30.0, 30.0),  # Alert
    ("TUCURU", "TUCURUI", "Norte", "RCU", 90.0, 90.0),  # Normal
    ("ITAIPU", "ITAIPU", "Sul", "FIO", None, None),  # Unclassified
]


def _raw_rows() -> list[dict]:
    rows = []
    for rid, name, subsystem, kind, first, last in RESERVOIRS:
        for day in range(DAYS):
            when = LAST_DAY - timedelta(days=DAYS - 1 - day)
            volume = None if first is None else first + (last - first) * day / (DAYS - 1)
            rows.append({
                "id_reservatorio": rid,
                "nom_reservatorio": f" {name} ",
                "nom_subsistema": subsystem,
                "nom_bacia": "PARANA",
                "nom_ree": "PARANA",
                "tip_reservatorio": kind,
                "din_instante": datetime.combine(when, datetime.min.time()),
                "val_nivelmontante": 100.0 + day,
                "val_volumeutilcon": volume,
                "val_vazaoafluente": 1000.0,
                "val_vazaodefluente": 800.0,
            })
    return rows


@pytest.fixture
def raw_frame() -> pl.DataFrame:
    """Raw readings as published by ONS (nanosecond timestamps, padded names)."""
    return pl.DataFrame(_raw_rows()).with_columns(pl.col("din_instante").cast(pl.Datetime("ns")))


@pytest.fixture
def registry_file(tmp_path):
    """Minimal ONS reservoir registry (RESERVATORIOS.parquet)."""
    path = tmp_path / "reservatorios.parquet"
    pl.DataFrame({
        "res_id": ["FURNAS", "SOBRAD", "OTHER1", "TUCURU", "ITAIPU"],
        "nom_reservatorio": ["FURNAS", "SOBRADINHO", "SERRA DA MESA", "TUCURUÍ", "ITAIPU"],
        "ceg": [
            "UHE.PH.MG.000001-1.01", "UHE.PH.BA.000002-2.01", "UHE.PH.GO.000003-3.01",
            "UHE.PH.PA.000004-4.01", "UHE.PH.PR.000005-5.01",
        ],
        "val_latitude": [-20.6, -9.4, -13.8, -3.8, -25.4],
        "val_longitude": [-46.3, -40.8, -48.3, -49.6, -54.6],
        "val_volutiltot": ["17217", "28669", "43250", "38982", "0"],
        "nom_rio": [" GRANDE ", "SAO FRANCISCO", "TOCANTINS", "TOCANTINS", "PARANA"],
    }).write_parquet(path)
    return path


@pytest.fixture
def dashboard_df(raw_frame, registry_file, tmp_path):
    """Dataset as the dashboard sees it: processed and joined with the registry."""
    from src.visualization import data

    source = tmp_path / "raw.parquet"
    raw_frame.write_parquet(source)
    return data.load_dataset(source, registry_file)
