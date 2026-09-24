from __future__ import annotations

from pathlib import Path

from app.collectors import google_play_books

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_parses_expected_transaction_count():
    txns = google_play_books.parse_file(FIXTURES_DIR / "google" / "sample_google_report.csv")
    assert len(txns) == 4


def test_refund_is_negative():
    txns = google_play_books.parse_file(FIXTURES_DIR / "google" / "sample_google_report.csv")
    refund = next(t for t in txns if "GP-002" in t.transaction_id)
    assert refund.quantity == -1
    assert refund.revenue == -2.50


def test_uses_publisher_proceeds_not_list_price():
    txns = google_play_books.parse_file(FIXTURES_DIR / "google" / "sample_google_report.csv")
    sale = next(t for t in txns if "GP-001" in t.transaction_id)
    assert sale.revenue == 5.00


def test_transaction_ids_are_unique():
    txns = google_play_books.parse_file(FIXTURES_DIR / "google" / "sample_google_report.csv")
    ids = [t.transaction_id for t in txns]
    assert len(ids) == len(set(ids))
