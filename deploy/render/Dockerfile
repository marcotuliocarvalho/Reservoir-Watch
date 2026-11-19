# Online demo for Render (free web service: 512 MB RAM, 0.1 CPU).
# Self-contained: no Airflow. The ingestion runs at build time for recent
# years only, and the image keeps just the prepared dashboard dataset, so the
# server stays far below 512 MB. A daily rebuild refreshes the data.
FROM python:3.12-slim

# First year shown in the demo. More years need more memory.
ARG DEMO_SINCE=2020

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HIDRIC_DATA_DIR=/app/data \
    HIDRIC_REGISTRY=/app/registry/reservatorios.parquet \
    POLARS_MAX_THREADS=2

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

RUN mkdir -p /app/registry \
    && python -c "import urllib.request; urllib.request.urlretrieve('https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/reservatorio/RESERVATORIOS.parquet', '/app/registry/reservatorios.parquet')"

COPY src ./src

# Download the recent years from ONS, then keep only the prepared dataset.
RUN HIDRIC_DATA_DIR=/tmp/ingest python -m src.ingestion --write --since "$DEMO_SINCE" \
    && python -m src.visualization --source /tmp/ingest/reservatorios_hidrologicos.parquet \
        --export /app/data/dashboard.parquet \
    && rm -rf /tmp/ingest

RUN useradd --create-home --uid 1000 dash && chown -R dash /app
USER dash

# Render sets PORT (default 10000). One worker: the dataset lives in memory.
# No --preload: Polars threads started before the fork deadlock the worker.
CMD ["sh", "-c", "exec gunicorn src.visualization.wsgi:server --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 --timeout 120"]
