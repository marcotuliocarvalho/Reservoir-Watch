# Water Dashboard

[![CI](https://github.com/marcotuliocarvalho/Reservoir-Watch/actions/workflows/ci.yml/badge.svg)](https://github.com/marcotuliocarvalho/Reservoir-Watch/actions/workflows/ci.yml)

Ingestion pipeline and interactive dashboard for the reservoirs of Brazil's
National Interconnected System (SIN), built on open data from
[ONS](https://dados.ons.org.br) (Operador Nacional do Sistema Elétrico).

- **Ingestion**: discovers the yearly Parquet files in the ONS catalog,
  downloads them, cleans them and writes one processed file. Runs daily in
  Airflow.
- **Dashboard**: a Dash app with a map of Brazil, criticality alerts, trends by
  region or subsystem, flows, a ranking of the lowest reservoirs and a
  detailed table.

## Architecture

```
ONS CKAN API ──> discover ──> download (1 task per year) ──> clean + transform ──> data/*.parquet ──> Dash dashboard
                 └─────────────── Airflow DAG: hidrico_ingestion (@daily) ───────────────┘
```

| Path | Role |
|------|------|
| `src/ingestion/catalog.py` | Lists the yearly Parquet URLs of the `dados-hidrologicos-res` dataset |
| `src/ingestion/reader.py` | Downloads and lazily scans Parquet files with Polars |
| `src/ingestion/cleaning.py` | Casts timestamps, drops rows without id or time and duplicated readings |
| `src/ingestion/transform.py` | Normalizes the upstream level by each reservoir's historical maximum |
| `src/ingestion/pipeline.py` | Plain pipeline functions and the Airflow DAG factory |
| `dags/hidrico_ingestion.py` | Airflow entry point |
| `src/visualization/` | Dash app: data prep, charts, layout, callbacks, theme |
| `Dockerfile` | Airflow image |
| `Dockerfile.dashboard` | Dashboard image (bundles the reservoir registry) |
| `docker-compose.yaml` | Full stack: `airflow` and `dashboard` services |
| `deploy/huggingface/` | Self-contained demo image for Hugging Face Spaces |
| `tests/` | Unit and smoke tests (pytest) |
| `.github/workflows/` | CI (lint, tests, DAG, Docker builds) and demo deploy |

## Dashboard features

- Single-screen layout on desktop (window at least 1100×600 px): filters in a
  left sidebar, KPIs on top and a 3×2 grid with the map, trend, alerts,
  reservoir in focus, flows / lowest levels / table (tabs) and analysis by area.
  Long lists scroll inside their card. Smaller screens fall back to one
  scrolling column.
- Filters by period, region, subsystem, REE, basin, reservoir type, status and current value range.
- Two metrics: **useful volume** (% of maximum useful volume) and **normalized level**.
- Map colored by area or by mean value, with reservoir markers by status. Click an area to filter and zoom.
- Criticality status for storage reservoirs (types RCU, RES, RBB), always by useful volume:

  | Status | Rule |
  |--------|------|
  | Critical | useful volume below 20% |
  | Alert | useful volume between 20% and 40% |
  | Watch | drop of 10 pp or more in 30 days |
  | Normal | no triggers |
  | Unclassified | run-of-river or no volume reading |

  These are reference thresholds, not an official ONS criterion.
- Light and dark theme, saved per browser.

## Requirements

- Python 3.12+
- Docker and Docker Compose (to run the full stack)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

The dashboard uses the ONS reservoir registry for coordinates, states and
capacity. Download it once (it is not versioned):

```bash
curl -o src/visualization/static/reservatorios.parquet \
  https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/reservatorio/RESERVATORIOS.parquet
```

Without this file the dashboard still runs, but the map and the region data stay empty.

## Running with Docker (recommended)

```bash
cp .env.example .env
mkdir -p data
docker compose up --build
```

This starts the full stack:

- Airflow: http://localhost:8080
- Dashboard: http://localhost:8050

The dashboard image downloads the reservoir registry at build time. The
dashboard waits until the first DAG run writes the processed dataset, then
starts. It loads the data once, so restart it to see new runs:
`docker compose restart dashboard`.

## Running the ingestion

### With Airflow

Run `docker compose up --build` as above. The `hidrico_ingestion` DAG runs daily and writes:

- `data/raw/DADOS_HIDROLOGICOS_RES_<year>.parquet`: raw yearly files. Closed years are downloaded only once; the current year is refreshed on every run.
- `data/reservatorios_hidrologicos.parquet`: the processed dataset.

To ingest only some years, trigger the DAG with the `years` param, for example `[2024, 2025]`.

### Without Airflow

```bash
python -m src.ingestion                    # all years, preview only
python -m src.ingestion 2024 2025          # some years, preview only
python -m src.ingestion --write            # download and write the dataset
```

Without `--write`, the pipeline runs in memory and prints a preview. With
`--write`, it downloads the yearly files (4 in parallel) to
`$HIDRIC_DATA_DIR/raw` and writes the processed dataset, like one DAG run.

## Running the dashboard

```bash
python -m src.visualization                          # reads HIDRIC_DATA_DIR, then ./data
python -m src.visualization --source "data/raw/*.parquet"
python -m src.visualization --port 8050 --debug
```

Open http://127.0.0.1:8050. `--source` takes a file, a directory or a glob
pattern. Raw ONS files go through the cleaning pipeline automatically.

## Tests

```bash
pip install -r requirements-dev.txt
ruff check .
pytest --cov=src
```

The tests use small synthetic frames shaped like the ONS files and never call
the network. The DAG test runs only when Airflow is installed (the CI has a
separate job for it).

## CI and online demo

GitHub Actions runs on every push and pull request:

- `ci.yml`: lint (ruff), tests with coverage, Airflow DAG import, and build of
  both Docker images.
- `deploy-demo.yml`: after CI passes on `main`, pushes the dashboard to a
  [Hugging Face Space](https://huggingface.co/docs/hub/spaces-sdks-docker)
  (free CPU tier, 16 GB RAM). It also runs daily to rebuild the Space with
  fresh ONS data.

The demo image (`deploy/huggingface/Dockerfile`) does not use Airflow: it runs
`python -m src.ingestion --write` at build time and serves the dashboard with
gunicorn. To enable the deploy, once:

1. Create a Hugging Face account and a token with write access at
   <https://huggingface.co/settings/tokens>.
2. In the GitHub repository, open Settings > Secrets and variables > Actions.
   Add the secret `HF_TOKEN` (the token) and the variable `HF_SPACE`
   (`<hf-user>/reservoir-watch`).
3. Run the "Deploy demo" workflow, or push to `main`. The Space is created on
   the first run. The first build takes about 5 minutes.

Free Spaces sleep after 48 hours without visits and wake up on the next visit.

## Configuration

| Variable | Default | Use |
|----------|---------|-----|
| `HIDRIC_URL` | `https://dados.ons.org.br/api/3/action/package_show` | ONS CKAN endpoint |
| `HIDRIC_DATASET_ID` | `dados-hidrologicos-res` | ONS dataset id |
| `HIDRIC_DATA_DIR` | `./data` | Where the DAG writes and the dashboard reads |
| `HIDRIC_REGISTRY` | `src/visualization/static/reservatorios.parquet` | Reservoir registry file |
| `AIRFLOW_UID` | `50000` | User id for the Airflow container (use `id -u`) |

## Data sources

- ONS: [Dados Hidrológicos de Reservatórios](https://dados.ons.org.br/dataset/dados-hidrologicos-res) and [Reservatórios](https://dados.ons.org.br/dataset/reservatorio).
- IBGE: state mesh used on the map.

The state–subsystem mapping on the map is approximate.

## Stack

Python · Polars · Dash · Plotly · Apache Airflow 3 · Docker
