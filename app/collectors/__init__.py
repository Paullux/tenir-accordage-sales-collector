from app.collectors import amazon_kdp, google_play_books, kobo

COLLECTORS = {
    "amazon": amazon_kdp,
    "kobo": kobo,
    "google": google_play_books,
}

PLATFORMS = tuple(COLLECTORS.keys())
