"""Kobo Writing Life adapter.

Import mode: reads the sales CSV exportable from the Kobo Writing Life
dashboard, or the monthly sales report. Column names are matched
case-insensitively against known aliases (see below) since Kobo has used
slightly different headers across report versions.

IMPORTANT — Fnac attribution: standard Kobo Writing Life reports do not
expose a reseller/retailer field that reliably identifies a sale as coming
specifically from the Fnac storefront (Fnac resells Kobo's catalogue through
Kobo's own distribution, but the sales report only reports the Kobo
ecosystem as a whole). This adapter therefore reports the entire total under
"kobo" and never fabricates a "fnac" breakdown. If Kobo ever adds a reliable
per-reseller field, extend `_COLUMNS` and split the total here — do not
guess a split in `app/stats.py`.
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

PLATFORM = "kobo"


def parse_file(path: Path) -> list[Transaction]:
    rows = read_rows(path)
    if not rows:
        return []

    header = rows[0]
    col_date = resolve_column(
        header, "Transaction Date", "Sale Date", "Date", "Transaction Month"
    )
    col_title = resolve_column(header, "Title", "Book Title")
    col_isbn = resolve_column(header, "ISBN", "ISBN13")
    col_country = resolve_column(header, "Country", "Sale Country")
    col_currency = resolve_column(header, "Currency", "Currency Code")
    col_units = resolve_column(
        header, "Net Units Sold", "Units Sold", "Quantity", "Net Quantity"
    )
    col_units_returned = resolve_column(header, "Units Returned", "Units Refunded")
    col_revenue = resolve_column(
        header, "Net Revenue", "Your Earnings", "Royalty", "Net Amount", "Amount"
    )
    col_transaction_id = resolve_column(header, "Transaction ID", "Order ID")

    if not col_date or not col_units or not col_revenue:
        raise ReportFormatError(
            "Kobo report is missing required columns "
            "(expected a date, a units column and a revenue/earnings column). "
            f"Found columns: {list(header.keys())}"
        )

    transactions: list[Transaction] = []

    for row in rows:
        title = clean_str(row.get(col_title, "")) if col_title else ""
        isbn = clean_str(row.get(col_isbn, "")) if col_isbn else None
        country = clean_str(row.get(col_country, "")) if col_country else None
        currency = (clean_str(row.get(col_currency, "")) if col_currency else "EUR").upper()
        currency = currency or "EUR"

        if not title and not isbn:
            continue

        try:
            txn_date = parse_date(row.get(col_date))
        except ReportFormatError:
            continue

        units_sold = parse_int(row.get(col_units, 0))
        units_returned = parse_int(row.get(col_units_returned, 0)) if col_units_returned else 0
        net_units = units_sold - abs(units_returned)

        revenue = parse_number(row.get(col_revenue, 0))

        transactions.append(
            Transaction(
                platform=PLATFORM,
                transaction_id=_transaction_id(
                    row, col_transaction_id, PLATFORM, txn_date, isbn, net_units, country,
                    revenue,
                ),
                transaction_date=txn_date,
                title=title,
                isbn=isbn or None,
                country=country or None,
                quantity=net_units,
                revenue=revenue,
                currency=currency,
                source=Source.IMPORT,
            )
        )

    return transactions


def _transaction_id(row, col_transaction_id, platform, txn_date, isbn, units, country,
                     amount) -> str:
    if col_transaction_id:
        raw_id = clean_str(row.get(col_transaction_id, ""))
        if raw_id:
            return f"{platform}:{raw_id}"
    return (
        f"{platform}:det:{txn_date.isoformat()}:{isbn or 'noisbn'}:{units}:"
        f"{country or 'na'}:{amount:.2f}"
    )
