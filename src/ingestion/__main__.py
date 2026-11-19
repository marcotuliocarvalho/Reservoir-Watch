"""Run with: python -m src.ingestion [--write] [--since YEAR | year ...]

Without ``--write`` the pipeline runs in memory and prints a preview. With
``--write`` it downloads the raw files and writes the processed dataset to
HIDRIC_DATA_DIR (default ./data), like one run of the Airflow DAG.
"""

import argparse
from datetime import date

from .config import IngestionConfig
from .pipeline import ingest_to_disk, run_ingestion


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="ONS reservoir data ingestion")
    parser.add_argument("years", nargs="*", type=int, help="Years to ingest (default: all)")
    parser.add_argument("--since", type=int, metavar="YEAR", help="Ingest YEAR up to the current year")
    parser.add_argument("--write", action="store_true", help="Download and write the processed dataset")
    args = parser.parse_args(argv)
    if args.since and args.years:
        parser.error("use either --since or a list of years")

    years = tuple(range(args.since, date.today().year + 1)) if args.since else tuple(args.years)
    config = IngestionConfig.from_env(years=years or None)
    if args.write:
        print(f"Wrote {ingest_to_disk(config)}")
        return

    data = run_ingestion(config).collect()
    print(data.head())
    print(data.shape)


if __name__ == "__main__":
    main()
