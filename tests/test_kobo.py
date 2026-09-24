from __future__ import annotations

from pathlib import Path

from app.collectors import kobo

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_parses_expected_transaction_count():
    txns = kobo.parse_file(FIXTURES_DIR / "kobo" / "sample_kobo_report.csv")
    assert len(txns) == 4


def test_net_units_accounts_for_returns():
    txns = kobo.parse_file(FIXTURES_DIR / "kobo" / "sample_kobo_report.csv")
    returned_row = next(t for t in txns if "KOBO-002" in t.transaction_id)
    assert returned_row.quantity == 1  # 2 sold - 1 returned


def test_currency_is_preserved_per_row():
    txns = kobo.parse_file(FIXTURES_DIR / "kobo" / "sample_kobo_report.csv")
    currencies = {t.currency for t in txns}
    assert currencies == {"EUR", "GBP"}


def test_transaction_ids_are_unique():
    txns = kobo.parse_file(FIXTURES_DIR / "kobo" / "sample_kobo_report.csv")
    ids = [t.transaction_id for t in txns]
    assert len(ids) == len(set(ids))
