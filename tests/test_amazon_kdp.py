from __future__ import annotations

from pathlib import Path

from app.collectors import amazon_kdp

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_parses_expected_transaction_count():
    txns = amazon_kdp.parse_file(FIXTURES_DIR / "amazon" / "sample_kdp_report.csv")
    # 4 "Standard" rows (2 books + 1 refund + 1 USD sale) + 1 KENP row
    assert len(txns) == 5


def test_kenp_excluded_from_quantity_and_revenue():
    txns = amazon_kdp.parse_file(FIXTURES_DIR / "amazon" / "sample_kdp_report.csv")
    kenp = [t for t in txns if t.kenp_pages > 0]
    assert len(kenp) == 1
    assert kenp[0].quantity == 0
    assert kenp[0].revenue == 0.0
    assert kenp[0].kenp_pages == 1200
    assert kenp[0].kenp_revenue == 3.50


def test_refund_is_negative_quantity():
    txns = amazon_kdp.parse_file(FIXTURES_DIR / "amazon" / "sample_kdp_report.csv")
    refund = [t for t in txns if t.quantity < 0]
    assert len(refund) == 1
    assert refund[0].quantity == -1
    assert refund[0].revenue == -2.10


def test_transaction_ids_are_unique():
    txns = amazon_kdp.parse_file(FIXTURES_DIR / "amazon" / "sample_kdp_report.csv")
    ids = [t.transaction_id for t in txns]
    assert len(ids) == len(set(ids))


def test_currency_is_preserved_per_row():
    txns = amazon_kdp.parse_file(FIXTURES_DIR / "amazon" / "sample_kdp_report.csv")
    currencies = {t.currency for t in txns}
    assert currencies == {"EUR", "USD"}
