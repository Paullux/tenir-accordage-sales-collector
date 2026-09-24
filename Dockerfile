# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app

# Install the package with the optional "browser" extra so Playwright is
# available for the platforms that opt into browser sync (AMAZON_BROWSER_SYNC=true
# etc.) — it stays unused (no Chromium launch, no extra network calls) when every
# *_BROWSER_SYNC flag is left at its default "false".
RUN pip install --no-cache-dir '.[browser]' \
    && playwright install --with-deps chromium

RUN groupadd --system collector && useradd --system --gid collector --home-dir /app collector \
    && mkdir -p /data/imports/amazon /data/imports/kobo /data/imports/google /data/sessions \
    && chown -R collector:collector /app /data

VOLUME ["/data"]
EXPOSE 8080

USER collector

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
