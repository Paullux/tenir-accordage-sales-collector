from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.responses import JSONResponse

from app.auth import require_bearer_token
from app.config import Settings, get_settings
from app.db import Database
from app.stats import build_stats, build_status
from app.sync import is_syncing, run_sync, scheduler_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("collector")


def get_db(settings: Settings = Depends(get_settings)) -> Database:
    return _database_for(settings)


_db_instances: dict[str, Database] = {}


def _database_for(settings: Settings) -> Database:
    key = str(settings.db_path)
    db = _db_instances.get(key)
    if db is None:
        db = Database(settings.db_path)
        _db_instances[key] = db
    return db


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_directories()
    db = _database_for(settings)

    scheduler_task = asyncio.create_task(scheduler_loop(db, settings))
    try:
        yield
    finally:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass


app = FastAPI(
    title="tenir-accordage-sales-collector",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/v1/status")
def get_status(settings: Settings = Depends(get_settings)) -> dict:
    db = _database_for(settings)
    return build_status(db)


@app.get("/v1/stats", dependencies=[Depends(require_bearer_token)])
def get_stats(settings: Settings = Depends(get_settings)) -> dict:
    db = _database_for(settings)
    return build_stats(db, settings)


@app.post("/v1/sync", dependencies=[Depends(require_bearer_token)])
async def trigger_sync(
    request: Request, settings: Settings = Depends(get_settings)
) -> Response:
    db = _database_for(settings)
    if is_syncing():
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"status": "already_running"},
        )

    async def _background() -> None:
        try:
            await run_sync(db, settings)
        except Exception:  # noqa: BLE001
            logger.exception("Background sync triggered via /v1/sync failed")

    asyncio.create_task(_background())
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"status": "started"})
