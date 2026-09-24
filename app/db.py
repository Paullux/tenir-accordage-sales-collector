from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.models import SyncStatus, Transaction

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    transaction_id TEXT NOT NULL,
    transaction_date TEXT NOT NULL,
    title TEXT NOT NULL,
    isbn TEXT,
    country TEXT,
    quantity INTEGER NOT NULL,
    revenue REAL NOT NULL,
    currency TEXT NOT NULL,
    revenue_eur REAL NOT NULL,
    source TEXT NOT NULL,
    matched_book INTEGER NOT NULL DEFAULT 0,
    imported_at TEXT NOT NULL,
    UNIQUE (platform, transaction_id)
);

CREATE INDEX IF NOT EXISTS idx_transactions_platform ON transactions (platform);
CREATE INDEX IF NOT EXISTS idx_transactions_matched ON transactions (matched_book);

CREATE TABLE IF NOT EXISTS processed_imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    transaction_count INTEGER NOT NULL DEFAULT 0,
    processed_at TEXT NOT NULL,
    UNIQUE (platform, filename, file_hash)
);

CREATE TABLE IF NOT EXISTS sync_state (
    platform TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    last_sync TEXT,
    last_error TEXT
);
"""

_lock = threading.Lock()


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    # -- imports ------------------------------------------------------

    def was_file_processed(self, platform: str, filename: str, file_hash: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM processed_imports WHERE platform = ? AND filename = ? "
                "AND file_hash = ?",
                (platform, filename, file_hash),
            ).fetchone()
            return row is not None

    def mark_file_processed(
        self, platform: str, filename: str, file_hash: str, transaction_count: int
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO processed_imports "
                "(platform, filename, file_hash, transaction_count, processed_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (platform, filename, file_hash, transaction_count, _now_iso()),
            )

    # -- transactions ---------------------------------------------------

    def upsert_transactions(self, transactions: list[Transaction], fx_rates: dict[str, float],
                             target_currency: str) -> int:
        """Insert transactions, ignoring ones already known (same platform +
        transaction_id). Returns the number of newly inserted rows."""
        inserted = 0
        with _lock, self.connect() as conn:
            for txn in transactions:
                rate = 1.0 if txn.currency.upper() == target_currency.upper() else fx_rates.get(
                    txn.currency.upper(), 1.0
                )
                revenue_eur = round(txn.revenue * rate, 4)
                cur = conn.execute(
                    "INSERT OR IGNORE INTO transactions "
                    "(platform, transaction_id, transaction_date, title, isbn, country, "
                    "quantity, revenue, currency, revenue_eur, source, matched_book, imported_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        txn.platform,
                        txn.transaction_id,
                        txn.transaction_date.isoformat(),
                        txn.title,
                        txn.isbn,
                        txn.country,
                        txn.quantity,
                        txn.revenue,
                        txn.currency.upper(),
                        revenue_eur,
                        txn.source.value,
                        1 if txn.matched_book else 0,
                        _now_iso(),
                    ),
                )
                if cur.rowcount:
                    inserted += 1
        return inserted

    # -- stats ------------------------------------------------------------

    def platform_totals(self, platform: str) -> tuple[int, float]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(quantity), 0) AS sales, "
                "COALESCE(SUM(revenue_eur), 0.0) AS revenue "
                "FROM transactions WHERE platform = ? AND matched_book = 1",
                (platform,),
            ).fetchone()
            return int(row["sales"]), round(float(row["revenue"]), 2)

    # -- sync state ---------------------------------------------------

    def set_sync_status(
        self, platform: str, status: SyncStatus, error: str | None = None,
        bump_last_sync: bool = False,
    ) -> None:
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT last_sync FROM sync_state WHERE platform = ?", (platform,)
            ).fetchone()
            last_sync = existing["last_sync"] if existing else None
            if bump_last_sync:
                last_sync = _now_iso()
            conn.execute(
                "INSERT INTO sync_state (platform, status, last_sync, last_error) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(platform) DO UPDATE SET status=excluded.status, "
                "last_sync=excluded.last_sync, last_error=excluded.last_error",
                (platform, status.value, last_sync, error),
            )

    def get_status(self) -> dict[str, dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM sync_state").fetchall()
        result = {}
        for row in rows:
            result[row["platform"]] = {
                "status": row["status"],
                "last_sync": row["last_sync"],
            }
        return result


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
