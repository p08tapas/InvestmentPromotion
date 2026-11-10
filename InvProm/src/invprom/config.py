from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="INVPROM_", extra="ignore")

    database_url: str = "sqlite:///./data/invprom.db"
    data_dir: Path = Path("./data")
    score_model_version: str = "wbidc-v1-banker-signals"

    @property
    def sector_taxonomy_path(self) -> Path:
        return self.data_dir / "sector_taxonomy.json"

    @property
    def government_incentives_path(self) -> Path:
        return self.data_dir / "government_incentives.json"

    @property
    def nse_subject_feeds_path(self) -> Path:
        return self.data_dir / "nse_subject_feeds.json"

    @property
    def nse_index_classifiers_path(self) -> Path:
        return self.data_dir / "nse_index_classifiers.json"

    @property
    def pdf_cache_dir(self) -> Path:
        return self.data_dir / "pdf_cache"


settings = Settings()
