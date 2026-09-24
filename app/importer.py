from __future__ import annotations

import logging

from app.bookfilter import apply_book_filter
from app.collectors import COLLECTORS
from app.collectors.base import ReportFormatError, file_hash
from app.config import Settings
from app.db import Database

logger = logging.getLogger("collector.importer")

_SUPPORTED_SUFFIXES = {".csv", ".tsv", ".txt", ".xlsx", ".xlsm"}


def import_platform_files(platform: str, db: Database, settings: Settings) -> int:
    """Scan /data/imports/<platform>/ for new report files, parse them, and
    persist newly-seen transactions. Returns the number of newly inserted
    transactions. Already-processed files (by content hash) are skipped.
    """
    module = COLLECTORS[platform]
    folder = settings.imports_path / platform
    folder.mkdir(parents=True, exist_ok=True)

    total_inserted = 0
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in _SUPPORTED_SUFFIXES:
            continue

        digest = file_hash(path)
        if db.was_file_processed(platform, path.name, digest):
            continue

        try:
            transactions = module.parse_file(path)
        except ReportFormatError:
            logger.exception("Failed to parse %s report %s", platform, path.name)
            continue

        apply_book_filter(transactions, settings)
        inserted = db.upsert_transactions(transactions, settings.fx_rates, settings.target_currency)
        db.mark_file_processed(platform, path.name, digest, len(transactions))
        total_inserted += inserted
        logger.info(
            "Imported %s: %s -> %d transactions parsed, %d new",
            platform, path.name, len(transactions), inserted,
        )

    return total_inserted
