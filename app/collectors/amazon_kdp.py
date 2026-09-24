"""Amazon KDP adapter.

Import mode: reads the "Combined Sales" / royalties report exportable from
KDP Reports (https://kdpreports.amazon.com) as CSV or XLSX. Column names vary
slightly by locale and by which KDP report you export, so columns are matched
case-insensitively against a list of known aliases (see `_COLUMNS` below).

KENP (Kindle Unlimited page reads) rows are recognised via the
"Transaction Type" / "Royalty Type" column and are EXCLUDED from `quantity`/
`revenue` for now, but their page count and estimated royalty are still
captured on `Transaction.kenp_pages` / `Transaction.kenp_revenue` for future
use, per the project spec.

Refunds appear as their own rows in KDP reports (negative "Net Units Sold"
and/or a "Refund"/"Order Cancellation" transaction type) and are folded in as
negative-quantity transactions, netting out naturally when summed.
"""

from __future__ import annotations

from pathlib import Path

from app.collectors.base import (
    ReportFormatError,
    clean_str,
    parse_date,
    parse_int,
    parse_number,
    read_rows,
    resolve_column,
)
from app.models import Source, Transaction

PLATFORM = "amazon"

_KENP_TYPES = {"kenp read", "kindle unlimited", "kenp"}


def parse_file(path: Path) -> list[Transaction]:
    rows = read_rows(path)
    if not rows:
        return []

    header = rows[0]
    col_date = resolve_column(header, "Royalty Date", "Date", "Transaction Date")
    col_title = resolve_column(header, "Title", "Book Title")
    col_isbn = resolve_column(header, "ASIN/ISBN", "ASIN", "ISBN")
    col_marketplace = resolve_column(header, "Marketplace", "Country")
    col_type = resolve_column(header, "Transaction Type", "Royalty Type")
    col_units = resolve_column(
        header, "Net Units Sold", "Units Sold", "Ordered Units", "Net Units"
    )
    col_royalty = resolve_column(
        header, "Royalty", "Royalty Amount", "Estimated Royalty", "Royalty (est.)"
    )
    col_currency = resolve_column(header, "Currency", "Currency Code")
    col_order_id = resolve_column(header, "Order ID", "Transaction ID")
    col_kenp_pages = resolve_column(
        header, "Kenp Read", "KENP Read", "Pages Read", "KENP Pages Read"
    )

    if not col_date or not col_units or not col_royalty:
        raise ReportFormatError(
            "Amazon KDP report is missing required columns "
            "(expected a date, a units column and a royalty column). "
            f"Found columns: {list(header.keys())}"
        )

    transactions: list[Transaction] = []

    for row in rows:
        txn_type = clean_str(row.get(col_type, "")).lower() if col_type else ""
        units = parse_int(row.get(col_units, 0))
        royalty = parse_number(row.get(col_royalty, 0))

        is_kenp = any(kenp in txn_type for kenp in _KENP_TYPES)

        title = clean_str(row.get(col_title, "")) if col_title else ""
        isbn = clean_str(row.get(col_isbn, "")) if col_isbn else None
        country = clean_str(row.get(col_marketplace, "")) if col_marketplace else None
        currency = clean_str(row.get(col_currency, "")) if col_currency else "USD"
        currency = currency.upper() or "USD"

        try:
            txn_date = parse_date(row.get(col_date))
        except ReportFormatError:
            continue

        if is_kenp:
            kenp_pages = parse_int(row.get(col_kenp_pages, 0)) if col_kenp_pages else 0
            transactions.append(
                Transaction(
                    platform=PLATFORM,
                    transaction_id=_transaction_id(
                        row, col_order_id, PLATFORM, txn_date, isbn, 0, country, 0.0
                    ),
                    transaction_date=txn_date,
                    title=title,
                    isbn=isbn or None,
                    country=country or None,
                    quantity=0,
                    revenue=0.0,
                    currency=currency,
                    source=Source.IMPORT,
                    kenp_pages=kenp_pages,
                    kenp_revenue=royalty,
                )
            )
            continue

        if not title and not isbn:
            continue

        transactions.append(
            Transaction(
                platform=PLATFORM,
                transaction_id=_transaction_id(
                    row, col_order_id, PLATFORM, txn_date, isbn, units, country, royalty
                ),
                transaction_date=txn_date,
                title=title,
                isbn=isbn or None,
                country=country or None,
                quantity=units,
                revenue=royalty,
                currency=currency,
                source=Source.IMPORT,
            )
        )

    return transactions


def _transaction_id(row, col_order_id, platform, txn_date, isbn, units, country, amount) -> str:
    if col_order_id:
        order_id = clean_str(row.get(col_order_id, ""))
        if order_id:
            return f"{platform}:{order_id}"
    return (
        f"{platform}:det:{txn_date.isoformat()}:{isbn or 'noisbn'}:{units}:"
        f"{country or 'na'}:{amount:.2f}"
    )
