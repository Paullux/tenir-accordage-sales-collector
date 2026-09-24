from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class Source(StrEnum):
    IMPORT = "import"
    BROWSER = "browser"


class SyncStatus(StrEnum):
    OK = "ok"
    NEEDS_AUTH = "needs_auth"
    ERROR = "error"
    NEVER_SYNCED = "never_synced"
    SYNCING = "syncing"


@dataclass(slots=True)
class Transaction:
    """Common internal representation produced by every platform adapter.

    `quantity` and `revenue` are already NET of refunds when the source
    report allows it (refund rows are represented as negative quantity /
    revenue transactions and folded in by the caller, or already netted by
    the adapter itself).
    """

    platform: str
    transaction_id: str
    transaction_date: date
    title: str
    isbn: str | None
    country: str | None
    quantity: int
    revenue: float
    currency: str
    source: Source = Source.IMPORT

    # Reserved for future Amazon KENP support. Not counted in `quantity`/
    # `revenue` today (see README / spec: KENP is excluded from classic sales).
    kenp_pages: int = 0
    kenp_revenue: float = 0.0

    # Set by the book filter before persisting: whether this transaction
    # matches the configured BOOK_ISBN / BOOK_TITLE.
    matched_book: bool = False

    extra: dict = field(default_factory=dict)
