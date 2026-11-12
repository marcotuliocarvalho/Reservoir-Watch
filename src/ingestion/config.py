"""Configuration for the hydrological data ingestion."""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

DEFAULT_API_URL = "https://dados.ons.org.br/api/3/action/package_show"
DEFAULT_DATASET_ID = "dados-hidrologicos-res"


@dataclass(frozen=True)
class IngestionConfig:
    """Settings used to discover, read and transform the ONS dataset."""

    api_url: str = DEFAULT_API_URL
    dataset_id: str = DEFAULT_DATASET_ID
    timeout: int = 30
    id_column: str = "id_reservatorio"
    time_column: str = "din_instante"
    target_column: str = "val_nivelmontante"
    years: tuple[int, ...] | None = field(default=None)

    @classmethod
    def from_env(cls, **overrides) -> "IngestionConfig":
        """Build the config from environment variables (.env supported)."""
        load_dotenv()
        values = {
            "api_url": os.getenv("HIDRIC_URL", DEFAULT_API_URL),
            "dataset_id": os.getenv("HIDRIC_DATASET_ID", DEFAULT_DATASET_ID),
        }
        values.update(overrides)
        return cls(**values)
