# tenir-accordage-sales-collector

Autonomous, **read-only** service that aggregates book sales from **Amazon
KDP**, **Kobo Writing Life** and **Google Play Books**, deduplicates them,
converts them to a single target currency, and exposes the totals as the
JSON feed expected by the [Book Sales Dashboard] WordPress plugin.

The collector never modifies anything on the sales platforms — it only
reads reports you drop into a folder (or, optionally, checks an
already-authenticated browser session).

[Book Sales Dashboard]: #wordpress-integration

## How it works

```
/data/imports/amazon/*.csv|.xlsx   ─┐
/data/imports/kobo/*.csv|.xlsx     ─┼─► importer ─► SQLite (/data/collector.sqlite) ─► /v1/stats
/data/imports/google/*.csv|.xlsx   ─┘         ▲
                                               │ (optional, off by default)
                                    Playwright session check
```

1. **Import mode** (primary, fully functional today): export a sales report
   from each platform's own dashboard and drop the file in
   `/data/imports/<platform>/`. The collector parses it, deduplicates
   transactions, filters to your configured book, and stores the result in
   SQLite. This mode needs no credentials at all.
2. **Browser mode** (optional, disabled by default): if you set
   `<PLATFORM>_BROWSER_SYNC=true` and have bootstrapped a Playwright session
   (see [below](#optional-browser-session-bootstrap)), the collector checks
   whether that session is still authenticated on each sync and reports
   `needs_auth` if not. Automatically *downloading* the report from the
   browser is left as an extension point for a future version — the three
   platforms above all provide downloadable reports today, so import mode
   covers the golden path; see [Why import mode comes first](#why-import-mode-comes-first).

`/v1/stats` **never** waits on any of this — it always returns immediately
from the SQLite cache.

## Data definitions

- **`sales`** — net copies sold (refunds already deducted when the report
  distinguishes them).
- **`revenue`** — author/publisher royalty, **not** gross list price,
  converted to `TARGET_CURRENCY` (default `EUR`).
- **KENP** (Kindle Unlimited page reads) is excluded from Amazon `sales`/
  `revenue` for now. The internal model already carries `kenp_pages` /
  `kenp_revenue` per transaction for a future version to surface.
- **Kobo vs. Fnac** — Fnac resells Kobo's catalogue through Kobo's own
  distribution. Kobo's sales reports do not include a reseller field that
  reliably attributes a given sale to Fnac, so `fnac` is **always** reported
  as `{"sales": 0, "revenue": 0.0}` rather than a guessed split. See
  [`app/collectors/kobo.py`](app/collectors/kobo.py). If your WordPress
  block needs a "Kobo / Fnac" combined label with two separate buy buttons,
  drive both buttons from the single `kobo` figure.
- **Deduplication** — every transaction gets a key. If the platform's report
  provides a transaction/order ID, that ID is used (`platform:id`).
  Otherwise a deterministic key is derived from
  `platform + date + ISBN + quantity + country + amount`, so re-importing
  the same file (or an overlapping export) never double-counts.
- **Currency conversion** — this service runs fully offline/read-only, so
  there is no live FX API call. `FX_RATES_TO_EUR` is a static JSON map of
  `"CODE": rate-to-target` applied when a transaction's currency isn't
  already `TARGET_CURRENCY`. Update it periodically; an unknown currency
  falls back to a 1:1 rate and logs a warning.
- **Google Play Books reporting delay** — Google documents its sales/
  transaction reports as arriving with roughly a 1-2 day delay. This is not
  a real-time feed; present it accordingly in the dashboard.

### Why import mode comes first

As of this writing, none of the three platforms publish a public API that
lets a service simply ask "what did I sell today": KDP Reports, Kobo Writing
Life and the Google Play Books Partner Center all center on **downloadable
report files**. Browser automation of platform dashboards is fragile (site
markup changes, and 2FA/CAPTCHA must never be bypassed — see below), so this
project's priority is a robust importer first, with browser sync as an
opt-in extra you can extend once your own report layout is confirmed.

## Report file formats

Real export headers vary by marketplace/locale and change occasionally, so
each adapter matches columns **case-insensitively against a list of known
aliases** rather than a fixed layout. If your export uses different headers
than the ones below, either rename the columns before dropping the file in
`/data/imports/<platform>/`, or extend the alias list in
`app/collectors/<platform>.py`.

| Platform | Expected columns (aliases matched) | Formats |
| --- | --- | --- |
| Amazon KDP | Royalty Date, Title, ASIN/ISBN, Marketplace, Transaction Type, Net Units Sold, Royalty, Currency, Order ID, KENP Read | `.csv`, `.xlsx` |
| Kobo Writing Life | Transaction Date, Title, ISBN, Country, Currency, Net Units Sold, Units Returned, Net Revenue, Transaction ID | `.csv`, `.xlsx` |
| Google Play Books | Transaction Date, Title, ISBN, Country of Sale, Currency, Transaction Type, Quantity, Publisher Proceeds, Transaction ID | `.csv`, `.tsv`, `.xlsx` |

See [`tests/fixtures/`](tests/fixtures/) for anonymized sample reports in
exactly the shape each adapter expects.

## Configuration

Copy [`.env.example`](.env.example) to `.env` and fill it in:

| Variable | Default | Purpose |
| --- | --- | --- |
| `BOOK_TITLE` | `Tenir l'accordage` | Title match (case/accent-insensitive substring) used when `BOOK_ISBN` is empty. |
| `BOOK_ISBN` | *(empty)* | If set, takes priority over `BOOK_TITLE` — only transactions with a matching ISBN are counted. |
| `TARGET_CURRENCY` | `EUR` | Currency of every figure in `/v1/stats`. |
| `FX_RATES_TO_EUR` | `{}` | Static JSON rate table, see above. |
| `COLLECTOR_API_TOKEN` | *(empty — required)* | Bearer token protecting every route except `/health`. |
| `SYNC_INTERVAL_MINUTES` | `360` | How often the background scheduler runs a sync. |
| `AMAZON_BROWSER_SYNC` / `KOBO_BROWSER_SYNC` / `GOOGLE_BROWSER_SYNC` | `false` | Enable the optional Playwright session check per platform. |
| `DATA_DIR` | `/data` | Where SQLite, imports and Playwright sessions live. |

Generate a token:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Running with Docker Compose

```bash
cp .env.example .env
# edit .env: set COLLECTOR_API_TOKEN at minimum
docker compose up -d
```

This pulls `ghcr.io/paullux/tenir-accordage-sales-collector:latest`, mounts
`./data` to `/data`, and exposes the API on `:8080`.

Drop a report file in, then either wait for the next scheduled sync or
trigger one immediately:

```bash
cp ~/Downloads/KDP_Royalties.csv ./data/imports/amazon/
curl -X POST https://collector.tenir.io/v1/sync \
  -H "Authorization: Bearer $COLLECTOR_API_TOKEN"
```

### TrueNAS (Docker Compose / Custom App)

1. Create a dataset for the collector's data, e.g. `/mnt/pool/apps/tenir-accordage-collector`.
2. In TrueNAS SCALE's "Custom App" (or the Docker Compose UI, depending on
   your version), point the image at
   `ghcr.io/paullux/tenir-accordage-sales-collector:latest`.
3. Mount the dataset above to `/data` inside the container.
4. Set the environment variables from the table above (`COLLECTOR_API_TOKEN`
   at minimum).
5. Expose container port `8080` — either directly, or behind TrueNAS's
   built-in reverse proxy / your own Traefik or Nginx Proxy Manager instance
   for HTTPS (see below).

### Coolify

Coolify can deploy this service either from the GHCR image or by pointing
it at this repository (it will build the included `Dockerfile`):

1. **New Resource → Docker Image** (simplest) and set the image to
   `ghcr.io/paullux/tenir-accordage-sales-collector:latest` — or
   **New Resource → Public/Private Git Repository** if you'd rather have
   Coolify build from source; it auto-detects the `Dockerfile`.
2. Under **Storages**, add a persistent volume mounted at `/data` (Coolify
   keeps this across redeploys — do **not** skip this, it's where
   `collector.sqlite`, imports and Playwright sessions live).
3. Under **Environment Variables**, add every variable from
   [`.env.example`](.env.example), at minimum `COLLECTOR_API_TOKEN`.
4. Set the container port to `8080` and attach your domain (e.g.
   `collector.tenir.io`) — Coolify's built-in Traefik proxy provisions and
   renews the Let's Encrypt certificate automatically, so no separate
   reverse-proxy setup is needed.
5. Deploy, then upload report files either via Coolify's file manager for
   that volume, `docker cp`, `scp`/`rsync` onto the host path backing the
   volume, or SFTP if you've enabled it — anything that lands the file in
   `/data/imports/<platform>/` on the running container's volume works,
   since the importer just watches that folder.
6. Trigger a sync the same way as any other deployment:
   `curl -X POST https://collector.tenir.io/v1/sync -H "Authorization: Bearer $COLLECTOR_API_TOKEN"`.

### HTTPS / reverse proxy (generic)

If you're not using Coolify's built-in proxy, put any TLS-terminating
reverse proxy (Traefik, Caddy, Nginx Proxy Manager, Nginx) in front of
container port `8080` and point your domain (e.g. `collector.tenir.io`) at
it. A minimal Caddy example:

```
collector.tenir.io {
    reverse_proxy localhost:8080
}
```

## API

### `GET /health` — public

```json
{"status": "ok"}
```

### `GET /v1/status` — public

```json
{
  "amazon": {"status": "ok", "last_sync": "2026-09-24T12:00:00Z"},
  "kobo": {"status": "ok", "last_sync": "2026-09-24T12:00:00Z"},
  "google": {"status": "needs_auth", "last_sync": null}
}
```

`status` is one of `ok`, `needs_auth`, `error`, `never_synced`.

### `GET /v1/stats` — requires `Authorization: Bearer <COLLECTOR_API_TOKEN>`

Always answers immediately from the SQLite cache, never blocking on any
platform:

```json
{
  "currency": "EUR",
  "platforms": {
    "amazon": {"sales": 0, "revenue": 0.0},
    "kobo": {"sales": 0, "revenue": 0.0},
    "fnac": {"sales": 0, "revenue": 0.0},
    "google": {"sales": 0, "revenue": 0.0}
  },
  "updated_at": "2026-09-24T12:00:00+02:00"
}
```

### `POST /v1/sync` — requires `Authorization: Bearer <COLLECTOR_API_TOKEN>`

Triggers a background sync (import pass over `/data/imports/**`, plus a
browser session check for any platform with `*_BROWSER_SYNC=true`) and
returns immediately (`202 Accepted`). Returns `409 Conflict` if a sync is
already running — two syncs never run concurrently.

## Manual report import (primary workflow)

1. Export the relevant report from the platform's own dashboard:
   - **Amazon KDP**: [kdpreports.amazon.com](https://kdpreports.amazon.com) → Reports → download the combined sales / royalties report (CSV or XLSX).
   - **Kobo Writing Life**: dashboard → Sales Reports → download the CSV, or the monthly sales report.
   - **Google Play Books Partner Center**: Reports → Sales/transaction report → export CSV/TSV.
2. Drop the file, unmodified, into `./data/imports/<amazon|kobo|google>/`.
3. Call `POST /v1/sync` (or wait for the next scheduled run). Already-seen
   files (by content hash) are skipped automatically, so it's safe to leave
   old exports in place.
4. Check `GET /v1/status` for per-platform sync health, and `GET /v1/stats`
   for the updated totals.

## Optional browser session bootstrap

Only needed if you want to enable `*_BROWSER_SYNC` for a platform. This
project never automates login, 2FA, or CAPTCHA-solving — a human logs in by
hand, once, in a real (visible) browser window, and the resulting session is
saved for later read-only checks:

```bash
pip install '.[browser]'
playwright install chromium
python scripts/bootstrap_browser_session.py amazon   # or: kobo / google
```

A browser window opens; log in normally (including any 2FA/CAPTCHA), then
press Enter in the terminal once you see your dashboard. The session is
saved to `/data/sessions/<platform>.json`. Set the corresponding
`*_BROWSER_SYNC=true` and restart the collector.

If a saved session expires, the collector marks that platform `needs_auth`
in `/v1/status` without blocking the other platforms — just re-run the
bootstrap script for that one platform.

## Security

- Every route except `/health` requires `Authorization: Bearer
  <COLLECTOR_API_TOKEN>`, compared with a constant-time comparison
  (`secrets.compare_digest`).
- The container runs as a non-root user.
- No password is ever stored in the image, in Git, in logs, or in any
  versioned config file — the only thing persisted for browser mode is a
  Playwright `storage_state` (cookies/local storage) file under
  `/data/sessions/`, created by the human-driven bootstrap script above.
- The collector is strictly read-only towards every sales platform: it only
  downloads/reads reports and checks session validity, never submits forms,
  changes settings, or performs any write action on KDP, Kobo or Google Play
  Books.

## Development

```bash
pip install -e '.[dev]'
ruff check .
pytest -v
```

Anonymized sample reports for all three platforms live in
[`tests/fixtures/`](tests/fixtures/); the test suite covers parsing,
refund handling, deduplication, book filtering, totals, Bearer-token
protection, and the exact JSON shape the WordPress plugin expects.

## WordPress integration

In the Book Sales Dashboard plugin settings:

```
URL du flux JSON : https://collector.tenir.io/v1/stats
Jeton Bearer      : <the same COLLECTOR_API_TOKEN>
```

The plugin's existing refresh mechanism polls `/v1/stats`, which always
answers instantly from cache — the collector's own scheduler (or your
`POST /v1/sync` calls) is what keeps that cache up to date in the
background.

## Project layout

```
app/
  main.py                FastAPI app, routes, lifespan/scheduler wiring
  config.py               Settings (env vars)
  auth.py                  Bearer token dependency
  db.py                    SQLite persistence + dedup
  bookfilter.py            ISBN/title matching against the configured book
  importer.py              Scans /data/imports/<platform>/ and persists new transactions
  stats.py                 Builds the /v1/stats and /v1/status payloads
  sync.py                  Orchestrates one sync pass + the background scheduler loop
  collectors/
    base.py                Shared CSV/TSV/XLSX parsing helpers
    amazon_kdp.py
    kobo.py
    google_play_books.py
  browser/
    base.py                Optional Playwright session-validity check
scripts/
  bootstrap_browser_session.py   Human-driven interactive login helper
tests/
  fixtures/                Anonymized sample reports per platform
```

## License

MIT — see [LICENSE](LICENSE).
