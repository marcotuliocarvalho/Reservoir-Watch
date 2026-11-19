"""Dash application factory."""

from pathlib import Path

import polars as pl
from dash import Dash

from .callbacks import register_callbacks
from .data import load_dataset
from .layout import build_layout

ASSETS = Path(__file__).parent / "assets"
FONTS = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"


def create_app(source: str | Path | None = None, df: pl.DataFrame | None = None) -> Dash:
    """Build the dashboard over ``df`` or over the Parquet files in ``source``."""
    df = df if df is not None else load_dataset(source)

    app = Dash(
        __name__,
        title="Water Dashboard",
        assets_folder=str(ASSETS),
        external_stylesheets=[FONTS],
        suppress_callback_exceptions=False,
    )
    app.layout = build_layout(df)
    register_callbacks(app, df)
    return app
