from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    book_title: str = "Tenir l'accordage"
    book_isbn: str = ""

    target_currency: str = "EUR"
    fx_rates_to_eur: str = "{}"

    collector_api_token: str = ""

    sync_interval_minutes: int = 360

    amazon_browser_sync: bool = False
    kobo_browser_sync: bool = False
    google_browser_sync: bool = False

    data_dir: str = "/data"

    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "info"

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)

    @property
    def db_path(self) -> Path:
        return self.data_path / "collector.sqlite"

    @property
    def imports_path(self) -> Path:
        return self.data_path / "imports"

    @property
    def sessions_path(self) -> Path:
        return self.data_path / "sessions"

    @property
    def fx_rates(self) -> dict[str, float]:
        try:
            rates = json.loads(self.fx_rates_to_eur or "{}")
        except json.JSONDecodeError:
            return {}
        return {str(k).upper(): float(v) for k, v in rates.items()}

    def browser_sync_enabled(self, platform: str) -> bool:
        return {
            "amazon": self.amazon_browser_sync,
            "kobo": self.kobo_browser_sync,
            "google": self.google_browser_sync,
        }.get(platform, False)

    def ensure_directories(self) -> None:
        for platform in ("amazon", "kobo", "google"):
            (self.imports_path / platform).mkdir(parents=True, exist_ok=True)
        self.sessions_path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
