from __future__ import annotations

import asyncio
import logging

from app.browser.base import sync_platform as browser_sync_platform
from app.collectors import PLATFORMS
from app.config import Settings
from app.db import Database
from app.importer import import_platform_files
from app.models import SyncStatus

logger = logging.getLogger("collector.sync")

_sync_lock = asyncio.Lock()


def is_syncing() -> bool:
    return _sync_lock.locked()


async def run_sync(db: Database, settings: Settings) -> bool:
    """Run one full sync pass (import mode for every platform, plus an
    optional browser check). Returns False without doing anything if a sync
    is already in progress, so callers never overlap two runs.
    """
    if _sync_lock.locked():
        logger.info("Sync already in progress, skipping this trigger")
        return False

    async with _sync_lock:
        for platform in PLATFORMS:
            await _sync_one_platform(platform, db, settings)
    return True


async def _sync_one_platform(platform: str, db: Database, settings: Settings) -> None:
    try:
        inserted = await asyncio.to_thread(import_platform_files, platform, db, settings)
        db.set_sync_status(platform, SyncStatus.OK, error=None, bump_last_sync=True)
        if inserted:
            logger.info("%s: %d new transactions imported", platform, inserted)
    except Exception as exc:  # noqa: BLE001 - one platform failing must not break the others
        logger.exception("Import failed for %s", platform)
        db.set_sync_status(platform, SyncStatus.ERROR, error=str(exc))

    if settings.browser_sync_enabled(platform):
        try:
            await browser_sync_platform(platform, settings, db)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Browser sync failed for %s", platform)
            db.set_sync_status(platform, SyncStatus.ERROR, error=str(exc))


async def scheduler_loop(db: Database, settings: Settings) -> None:
    """Background task: runs a sync every SYNC_INTERVAL_MINUTES."""
    interval = max(1, settings.sync_interval_minutes) * 60
    while True:
        try:
            await run_sync(db, settings)
        except Exception:  # noqa: BLE001 - the scheduler loop must never die
            logger.exception("Scheduled sync failed")
        await asyncio.sleep(interval)
