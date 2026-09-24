from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.db import Database
from app.importer import import_platform_files

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _seed(platform: str, filename: str, data_dir: Path, db: Database, settings: Settings):
    dest = data_dir / "imports" / platform / filename
    dest.write_bytes((FIXTURES_DIR / platform / filename).read_bytes())
    import_platform_files(platform, db, settings)


def test_only_configured_book_is_counted(settings: Settings, data_dir: Path, db: Database):
    _seed("amazon", "sample_kdp_report.csv", data_dir, db, settings)
    sales, _revenue = db.platform_totals("amazon")
    # "Un Autre Livre" (5 units) must be excluded, only "Tenir l'accordage" rows count.
    assert sales == 4  # 3 (sale) - 1 (refund) + 2 (USD sale) = 4


def test_amazon_totals_with_fx_conversion(settings: Settings, data_dir: Path, db: Database):
    _seed("amazon", "sample_kdp_report.csv", data_dir, db, settings)
    sales, revenue = db.platform_totals("amazon")
    assert sales == 4
    assert revenue == 7.8  # 6.30 - 2.10 + (4.00 * 0.9 USD->EUR)


def test_kobo_totals_with_fx_conversion(settings: Settings, data_dir: Path, db: Database):
    _seed("kobo", "sample_kobo_report.csv", data_dir, db, settings)
    sales, revenue = db.platform_totals("kobo")
    assert sales == 6  # 4 + (2-1) + 1
    assert revenue == 10.1  # 7.20 + 1.80 + (1.00 * 1.1 GBP->EUR)


def test_google_totals_with_refund(settings: Settings, data_dir: Path, db: Database):
    _seed("google", "sample_google_report.csv", data_dir, db, settings)
    sales, revenue = db.platform_totals("google")
    assert sales == 2  # 2 - 1 + 1
    assert revenue == 5.2  # 5.00 - 2.50 + (3.00 * 0.9 USD->EUR)


def test_isbn_filter_overrides_title(settings: Settings, data_dir: Path, db: Database):
    isbn_settings = Settings(
        **{**settings.model_dump(), "book_isbn": "978-1-234-567890", "book_title": ""}
    )
    _seed("amazon", "sample_kdp_report.csv", data_dir, db, isbn_settings)
    sales, _revenue = db.platform_totals("amazon")
    assert sales == 4
