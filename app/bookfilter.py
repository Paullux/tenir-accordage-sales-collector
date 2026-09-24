from __future__ import annotations

import unicodedata

from app.config import Settings
from app.models import Transaction


def _normalize_isbn(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum()).upper()


def _normalize_title(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.casefold().split())


def matches_book(txn: Transaction, settings: Settings) -> bool:
    """A transaction matches the configured book if its ISBN matches
    BOOK_ISBN (when set), otherwise if its title matches BOOK_TITLE.
    """
    isbn_filter = (settings.book_isbn or "").strip()
    if isbn_filter:
        if not txn.isbn:
            return False
        return _normalize_isbn(txn.isbn) == _normalize_isbn(isbn_filter)

    title_filter = (settings.book_title or "").strip()
    if not title_filter:
        return True
    if not txn.title:
        return False
    return _normalize_title(title_filter) in _normalize_title(txn.title)


def apply_book_filter(transactions: list[Transaction], settings: Settings) -> list[Transaction]:
    for txn in transactions:
        txn.matched_book = matches_book(txn, settings)
    return transactions
