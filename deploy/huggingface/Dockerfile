# Online demo for Hugging Face Spaces (Docker SDK, free CPU tier).
# Self-contained: no Airflow. The ingestion runs once at build time and the
# processed dataset is baked into the image. A daily rebuild refreshes it.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HIDRIC_DATA_DIR=/app/data \
    HIDRIC_REGISTRY=/app/registry/reservatorios.parquet

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

RUN mkdir -p /app/registry \
    && python -c "import urllib.request; urllib.request.urlretrieve('https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/reservatorio/RESERVATORIOS.parquet', '/app/registry/reservatorios.parquet')"

COPY src ./src

# Download every year from ONS and keep only the processed file.
RUN python -m src.ingestion --write && rm -rf /app/data/raw

# Spaces run the container as uid 1000.
RUN useradd --create-home --uid 1000 user && chown -R user /app
USER user

EXPOSE 7860

# One worker: the dataset lives in memory (about 2.5 GB), so more workers
# would multiply it. Threads handle concurrent callbacks.
CMD ["gunicorn", "src.visualization.wsgi:server", "--bind", "0.0.0.0:7860", "--workers", "1", "--threads", "8", "--timeout", "120", "--preload"]
