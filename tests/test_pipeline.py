from datetime import date

import polars as pl
import pytest

from src.ingestion import __main__ as cli
from src.ingestion import catalog, pipeline, reader
from src.ingestion.config import IngestionConfig


def test_process_cleans_and_normalizes(raw_frame):
    duplicated = pl.concat([raw_frame, raw_frame.head(3)])

    result = pipeline.process(duplicated.lazy(), IngestionConfig()).collect()

    assert result.height == raw_frame.height
    assert result.schema["din_instante"] == pl.Datetime("us")
    assert result["normalized_val_nivelmontante"].max() == 1.0


def test_write_processed_is_atomic(raw_frame, tmp_path):
    source = tmp_path / "raw.parquet"
    raw_frame.write_parquet(source)
    output = tmp_path / "out" / pipeline.OUTPUT_NAME

    written = pipeline.write_processed([source], output, IngestionConfig())

    assert written == output
    assert pl.read_parquet(output).height == raw_frame.height
    assert not output.with_suffix(".part").exists()


def test_fetch_year_skips_closed_year_on_disk(tmp_path, monkeypatch):
    existing = tmp_path / "DADOS_2020.parquet"
    existing.write_bytes(b"old")
    monkeypatch.setattr(reader, "download_parquet", lambda *a, **k: pytest.fail("should not download"))

    assert pipeline.fetch_year("https://x/DADOS_2020.parquet", tmp_path) == existing


def test_fetch_year_refreshes_current_year(tmp_path, monkeypatch):
    name = f"DADOS_{date.today().year}.parquet"
    (tmp_path / name).write_bytes(b"old")
    downloaded = []
    monkeypatch.setattr(reader, "download_parquet", lambda url, d, timeout: downloaded.append(url) or d / name)

    pipeline.fetch_year(f"https://x/{name}", tmp_path)

    assert downloaded == [f"https://x/{name}"]


def test_data_dir_reads_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HIDRIC_DATA_DIR", str(tmp_path))
    assert pipeline.data_dir() == tmp_path


@pytest.fixture
def fake_catalog(raw_frame, tmp_path, monkeypatch):
    """Serve the synthetic frame as two yearly files from a fake ONS catalog."""
    sources = tmp_path / "ons"
    sources.mkdir()
    urls = []
    for year, part in zip((2024, 2025), raw_frame.partition_by("nom_subsistema")[:2], strict=True):
        path = sources / f"DADOS_HIDROLOGICOS_RES_{year}.parquet"
        part.write_parquet(path)
        urls.append(str(path))

    def fake_download(url, dest_dir, timeout=30):
        dest_dir.mkdir(parents=True, exist_ok=True)
        target = dest_dir / url.rsplit("/", 1)[-1]
        target.write_bytes(open(url, "rb").read())
        return target

    monkeypatch.setattr(catalog, "get_parquet_urls", lambda config: urls)
    monkeypatch.setattr(reader, "download_parquet", fake_download)
    return urls


def test_ingest_to_disk_writes_processed_dataset(fake_catalog, tmp_path):
    root = tmp_path / "data"

    output = pipeline.ingest_to_disk(IngestionConfig(), root)

    assert output == root / pipeline.OUTPUT_NAME
    assert sorted(p.name for p in (root / "raw").iterdir()) == [
        "DADOS_HIDROLOGICOS_RES_2024.parquet", "DADOS_HIDROLOGICOS_RES_2025.parquet",
    ]
    assert "normalized_val_nivelmontante" in pl.read_parquet(output).columns


def test_ingest_to_disk_fails_on_empty_catalog(monkeypatch, tmp_path):
    monkeypatch.setattr(catalog, "get_parquet_urls", lambda config: [])
    with pytest.raises(ValueError):
        pipeline.ingest_to_disk(IngestionConfig(), tmp_path)


def test_cli_write(fake_catalog, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HIDRIC_DATA_DIR", str(tmp_path / "data"))

    cli.main(["--write", "2024"])

    assert (tmp_path / "data" / pipeline.OUTPUT_NAME).is_file()
    assert "Wrote" in capsys.readouterr().out


def test_dag_structure():
    pytest.importorskip("airflow.sdk")
    dag = pipeline.build_dag()
    assert dag.dag_id == pipeline.DAG_ID
    assert set(dag.task_ids) == {"discover", "download", "transform_and_save"}


def test_cli_since_selects_years_up_to_now(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "run_ingestion", lambda config: seen.setdefault("years", config.years) and pl.LazyFrame())

    cli.main(["--since", "2023"])

    assert seen["years"] == tuple(range(2023, date.today().year + 1))


def test_cli_rejects_since_with_years():
    with pytest.raises(SystemExit):
        cli.main(["--since", "2023", "2024"])
