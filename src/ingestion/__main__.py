"""Run with: python -m src.ingestion [year ...]"""

import sys

from .config import IngestionConfig
from .pipeline import run_ingestion


def main() -> None:
    years = tuple(int(arg) for arg in sys.argv[1:]) or None
    config = IngestionConfig.from_env(years=years)
    data = run_ingestion(config).collect()
    print(data.head())
    print(data.shape)


if __name__ == "__main__":
    main()
