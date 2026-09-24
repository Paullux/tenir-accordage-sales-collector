#!/usr/bin/env python3
"""Interactive Playwright session bootstrap.

Opens a real, visible browser window so a human can log in to a sales
platform by hand (including any 2FA/CAPTCHA challenge), then saves the
resulting session (cookies + local storage) to /data/sessions/<platform>.json
so the collector can reuse it for read-only browser checks.

This script NEVER stores or reads a password, and never attempts to solve a
CAPTCHA or 2FA challenge itself — a person completes the login in the
opened window.

Usage (run on a machine with a display, or via VNC/X11 forwarding into the
container — it will not work in a purely headless environment since you
need to see and use the login page):

    python scripts/bootstrap_browser_session.py amazon
    python scripts/bootstrap_browser_session.py kobo
    python scripts/bootstrap_browser_session.py google
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.browser.base import PLATFORM_URLS, session_path  # noqa: E402
from app.config import get_settings  # noqa: E402


async def main(platform: str) -> None:
    if platform not in PLATFORM_URLS:
        print(f"Unknown platform '{platform}'. Choose one of: {', '.join(PLATFORM_URLS)}")
        raise SystemExit(1)

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print(
            "Playwright is not installed. Install the 'browser' extra first:\n"
            "  pip install '.[browser]' && playwright install chromium"
        )
        raise SystemExit(1) from None

    settings = get_settings()
    settings.ensure_directories()
    out_path = session_path(settings, platform)

    print(f"Opening {PLATFORM_URLS[platform]} — log in manually in the window that opens.")
    print("Complete any 2FA/CAPTCHA yourself. When you're fully logged in and see your")
    print("dashboard, come back to this terminal and press Enter.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(PLATFORM_URLS[platform])

        prompt = "\nPress Enter once logged in... "
        await asyncio.get_event_loop().run_in_executor(None, input, prompt)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        await context.storage_state(path=str(out_path))
        await browser.close()

    print(f"Session saved to {out_path}")
    print(f"Set {platform.upper()}_BROWSER_SYNC=true to enable browser checks for this platform.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <amazon|kobo|google>")
        raise SystemExit(1)
    asyncio.run(main(sys.argv[1]))
