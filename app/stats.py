from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.config import Settings
from app.db import Database

# Fnac resells Kobo's catalogue through Kobo's own distribution, but Kobo's
# sales reports do not expose a reseller field that reliably attributes a
# sale to Fnac specifically (see app/collectors/kobo.py). Rather than guess,
# "fnac" is always reported as zero until a trustworthy source exists.
_FNAC_PLACEHOLDER = {"sales": 0, "revenue": 0.0}


def build_stats(db: Database, settings: Settings) -> dict:
    platforms = {}
    for platform in ("amazon", "kobo", "google"):
        sales, revenue = db.platform_totals(platform)
        platforms[platform] = {"sales": sales, "revenue": revenue}

    platforms["fnac"] = dict(_FNAC_PLACEHOLDER)

    return {
        "currency": settings.target_currency,
        "platforms": {
            "amazon": platforms["amazon"],
            "kobo": platforms["kobo"],
            "fnac": platforms["fnac"],
            "google": platforms["google"],
        },
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def is_stale(db: Database, settings: Settings) -> bool:
    """True if any platform was never synced or its last sync is older than
    STALE_AFTER_MINUTES."""
    known = db.get_status()
    threshold = datetime.now(UTC) - timedelta(minutes=settings.stale_after_minutes)
    for platform in ("amazon", "kobo", "google"):
        last = (known.get(platform) or {}).get("last_sync")
        if not last:
            return True
        if datetime.fromisoformat(last.replace("Z", "+00:00")) < threshold:
            return True
    return False


def build_status(db: Database) -> dict:
    known = db.get_status()
    result = {}
    for platform in ("amazon", "kobo", "google"):
        entry = known.get(platform)
        if entry is None:
            result[platform] = {"status": "never_synced", "last_sync": None}
        else:
            result[platform] = {"status": entry["status"], "last_sync": entry["last_sync"]}
    return result
