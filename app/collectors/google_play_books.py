"""Google Play Books Partner Center adapter.

Import mode: reads the sales/transaction report exportable from Google Play
Books Partner Center as CSV/TSV. Google publishes these reports with a
documented ~1-2 day delay, so downstream consumers (the WordPress dashboard)
should not present this feed as strictly real-time.

Refunds appear as their own rows with a transaction-type of "Refund"/"Chargeback"
and are folded in as negative-quantity/negative-revenue transactions so sums
net out naturally.

Publisher revenue (not the gross list price) is used for `revenue`, matching
whichever "publisher proceeds" / earnings column the export provides.
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

PLATFORM = "google"

_REFUND_TYPES = {"refund", "chargeback", "return"}


def parse_file(path: Path) -> list[Transaction]:
    rows = read_rows(path)
    if not rows:
        return []

    header = rows[0]
    col_date = resolve_column(header, "Transaction Date", "Order Date", "Date")
    col_title = resolve_column(header, "Title", "Product Title", "Book Title")
    col_isbn = resolve_column(header, "ISBN", "ISBN-13", "Product ID")
    col_country = resolve_column(header, "Country of Sale", "Country", "Buyer Country")
    col_currency = resolve_column(
        header, "Currency", "Merchant Currency", "Amount Currency"
    )
    col_type = resolve_column(header, "Transaction Type", "Description")
    col_quantity = resolve_column(header, "Quantity", "Units")
    col_revenue = resolve_column(
        header,
        "Publisher Proceeds",
        "Publisher Revenue",
        "Amount (Merchant Currency)",
        "Earnings",
        "Net Amount",
    )
    col_transaction_id = resolve_column(
        header, "Transaction ID", "Order Number", "Order ID"
    )

    if not col_date or not col_revenue:
        raise ReportFormatError(
            "Google Play Books report is missing required columns "
            "(expected a date column and a publisher revenue column). "
            f"Found columns: {list(header.keys())}"
        )

    transactions: list[Transaction] = []

    for row in rows:
        title = clean_str(row.get(col_title, "")) if col_title else ""
        isbn = clean_str(row.get(col_isbn, "")) if col_isbn else None
        country = clean_str(row.get(col_country, "")) if col_country else None
        currency = (clean_str(row.get(col_currency, "")) if col_currency else "USD").upper()
        currency = currency or "USD"
        txn_type = clean_str(row.get(col_type, "")).lower() if col_type else ""

        if not title and not isbn:
            continue

        try:
            txn_date = parse_date(row.get(col_date))
        except ReportFormatError:
            continue

        quantity = parse_int(row.get(col_quantity, 1)) if col_quantity else 1
        revenue = parse_number(row.get(col_revenue, 0))

        is_refund = any(kind in txn_type for kind in _REFUND_TYPES) or revenue < 0
        if is_refund:
            quantity = -abs(quantity)
            revenue = -abs(revenue)

        transactions.append(
            Transaction(
                platform=PLATFORM,
                transaction_id=_transaction_id(
                    row, col_transaction_id, PLATFORM, txn_date, isbn, quantity, country,
                    revenue,
                ),
                transaction_date=txn_date,
                title=title,
                isbn=isbn or None,
                country=country or None,
                quantity=quantity,
                revenue=revenue,
                currency=currency,
                source=Source.IMPORT,
            )
        )

    return transactions


def _transaction_id(row, col_transaction_id, platform, txn_date, isbn, quantity, country,
                     amount) -> str:
    if col_transaction_id:
        raw_id = clean_str(row.get(col_transaction_id, ""))
        if raw_id:
            return f"{platform}:{raw_id}"
    return (
        f"{platform}:det:{txn_date.isoformat()}:{isbn or 'noisbn'}:{quantity}:"
        f"{country or 'na'}:{amount:.2f}"
    )
