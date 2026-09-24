"""Optional Playwright-based browser automation.

This module is deliberately conservative: as documented in the project spec,
import mode (dropping report files in /data/imports/<platform>/) must remain
fully functional on its own, and browser automation is an opt-in extra that
is only attempted when the platform's own report download UI can't be
replaced by an official API.

What this scaffold does today:
  1. Checks whether a Playwright `storage_state` session was saved for the
     platform (via `scripts/bootstrap_browser_session.py`, run interactively
     by a human — this project never automates login, 2FA or CAPTCHA).
  2. If no session exists, or the saved session is no longer authenticated,
     marks the platform `needs_auth` without blocking the other platforms.
  3. If the session is valid, it is left to a per-platform hook to actually
     download report files into /data/imports/<platform>/ for the importer
     to pick up on the next pass. That download step is intentionally left
     as a `NotImplementedError` extension point for now (see README) — site
     markup changes too often to hard-code selectors without being able to
     test against the live, authenticated site, and the project priority is
     import mode first.

Nothing here ever types a password, solves a CAPTCHA, or answers a 2FA
prompt: those steps only happen in the human-driven bootstrap script.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.config import Settings
from app.db import Database
from app.models import SyncStatus

logger = logging.getLogger("collector.browser")

PLATFORM_URLS = {
    "amazon": "https://kdpreports.amazon.com",
    "kobo": "https://www.kobo.com/writinglife",
    "google": "https://play.google.com/books/publish",
}

# Substrings that, if present in the post-navigation URL, indicate the saved
# session is no longer authenticated and we landed back on a login page.
_LOGIN_URL_MARKERS = ("signin", "login", "accounts.google.com", "ap/signin")


def session_path(settings: Settings, platform: str) -> Path:
    return settings.sessions_path / f"{platform}.json"


async def sync_platform(platform: str, settings: Settings, db: Database) -> None:
    if not settings.browser_sync_enabled(platform):
        return

    state_file = session_path(settings, platform)
    if not state_file.exists():
        db.set_sync_status(
            platform,
            SyncStatus.NEEDS_AUTH,
            error="No saved browser session. Run scripts/bootstrap_browser_session.py "
            f"{platform} to log in interactively.",
        )
        return

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        db.set_sync_status(
            platform,
            SyncStatus.ERROR,
            error="Playwright is not installed in this image (browser sync requires the "
            "'browser' extra).",
        )
        return

    url = PLATFORM_URLS[platform]
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(storage_state=str(state_file))
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                authenticated = not any(marker in page.url.lower() for marker in _LOGIN_URL_MARKERS)
                await context.storage_state(path=str(state_file))
            finally:
                await browser.close()
    except Exception as exc:  # noqa: BLE001 - surface as needs_auth/error, never crash the sync
        logger.warning("Browser sync check failed for %s: %s", platform, exc)
        db.set_sync_status(platform, SyncStatus.ERROR, error=str(exc))
        return

    if not authenticated:
        db.set_sync_status(
            platform,
            SyncStatus.NEEDS_AUTH,
            error="Saved session expired. Re-run scripts/bootstrap_browser_session.py "
            f"{platform}.",
        )
        return

    logger.info(
        "%s: browser session is authenticated, but automatic report download is not "
        "implemented yet in this version — use import mode "
        "(/data/imports/%s/) in the meantime.",
        platform, platform,
    )
    db.set_sync_status(platform, SyncStatus.OK, error=None, bump_last_sync=True)
