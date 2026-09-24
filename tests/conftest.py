from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.db import Database

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_TOKEN = "test-secret-token-0123456789"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    (d / "imports" / "amazon").mkdir(parents=True)
    (d / "imports" / "kobo").mkdir(parents=True)
    (d / "imports" / "google").mkdir(parents=True)
    (d / "sessions").mkdir(parents=True)
    return d


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(
        data_dir=str(data_dir),
        book_title="Tenir l'accordage",
        book_isbn="",
        target_currency="EUR",
        fx_rates_to_eur='{"USD": 0.9, "GBP": 1.1}',
        collector_api_token=TEST_TOKEN,
        sync_interval_minutes=360,
    )


@pytest.fixture
def db(settings: Settings) -> Database:
    return Database(settings.db_path)


def copy_fixture(platform: str, name: str, data_dir: Path) -> Path:
    src = FIXTURES_DIR / platform / name
    dest = data_dir / "imports" / platform / name
    shutil.copyfile(src, dest)
    return dest


@pytest.fixture
def app_client(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    import os

    env_backup = {
        k: os.environ.get(k)
        for k in ("DATA_DIR", "COLLECTOR_API_TOKEN", "BOOK_TITLE", "BOOK_ISBN",
                  "TARGET_CURRENCY", "FX_RATES_TO_EUR")
    }
    os.environ["DATA_DIR"] = str(data_dir)
    os.environ["COLLECTOR_API_TOKEN"] = TEST_TOKEN
    os.environ["BOOK_TITLE"] = "Tenir l'accordage"
    os.environ["BOOK_ISBN"] = ""
    os.environ["TARGET_CURRENCY"] = "EUR"
    os.environ["FX_RATES_TO_EUR"] = '{"USD": 0.9, "GBP": 1.1}'
    get_settings.cache_clear()

    import app.main as main_module

    async def _noop_scheduler(db, settings):
        return None

    monkeypatch.setattr(main_module, "scheduler_loop", _noop_scheduler)
    main_module._db_instances.clear()

    with TestClient(main_module.app) as client:
        yield client

    main_module._db_instances.clear()
    get_settings.cache_clear()
    for k, v in env_backup.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
