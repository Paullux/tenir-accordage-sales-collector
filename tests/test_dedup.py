from __future__ import annotations

from pathlib import Path

from app.bookfilter import apply_book_filter
from app.collectors import amazon_kdp
from app.config import Settings
from app.db import Database
from app.importer import import_platform_files

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_reimporting_same_file_does_not_duplicate(settings: Settings, data_dir: Path,
                                                    db: Database):
    dest = data_dir / "imports" / "amazon" / "sample_kdp_report.csv"
    dest.write_bytes((FIXTURES_DIR / "amazon" / "sample_kdp_report.csv").read_bytes())

    first = import_platform_files("amazon", db, settings)
    second = import_platform_files("amazon", db, settings)

    assert first > 0
    assert second == 0

    with db.connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"]
    assert count == first


def test_upsert_ignores_same_deterministic_id_twice(settings: Settings, db: Database):
    txns = amazon_kdp.parse_file(FIXTURES_DIR / "amazon" / "sample_kdp_report.csv")
    apply_book_filter(txns, settings)

    inserted_1 = db.upsert_transactions(txns, settings.fx_rates, settings.target_currency)
    inserted_2 = db.upsert_transactions(txns, settings.fx_rates, settings.target_currency)

    assert inserted_1 == len(txns)
    assert inserted_2 == 0
