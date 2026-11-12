"""Ingestion of the ONS hydrological reservoir data."""

from .config import IngestionConfig
from .pipeline import load_raw, run_ingestion

__all__ = ["IngestionConfig", "load_raw", "run_ingestion"]
