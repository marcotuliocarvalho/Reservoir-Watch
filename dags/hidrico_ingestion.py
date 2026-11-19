"""Airflow entry point: the DAG lives in src/ingestion/pipeline.py."""

from src.ingestion.pipeline import build_dag

dag = build_dag()
