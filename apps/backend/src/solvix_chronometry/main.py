"""FastAPI-приложение Edge-сервера."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from solvix_chronometry import __version__
from solvix_chronometry.config import settings
from solvix_chronometry.api.auth import router as auth_router
from solvix_chronometry.ws.router import router as ws_router
from solvix_chronometry.api.dashboard import router as dashboard_router
from solvix_chronometry.api.parts import router as parts_router
from solvix_chronometry.api.batches import router as batches_router
from solvix_chronometry.api.shifts import router as shifts_router
from solvix_chronometry.api.badges import router as badges_router
from solvix_chronometry.api.users import router as users_router
from solvix_chronometry.api.search import router as search_router
from solvix_chronometry.api.timelines import router as timelines_router
from solvix_chronometry.api.analytics import router as analytics_router
from solvix_chronometry.api.stations import router as stations_router
from solvix_chronometry.mqtt.subscriber import run_subscriber
from solvix_chronometry.watchdog import run_watchdog

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # На старте — запускаем все фоновые задачи.
    subscriber_task = asyncio.create_task(run_subscriber(), name="mqtt-subscriber")
    logger.info("MQTT subscriber task started")

    watchdog_task = asyncio.create_task(run_watchdog(), name="watchdog")
    logger.info("Watchdog task started")

    background_tasks = [subscriber_task, watchdog_task]

    try:
        yield
    finally:
        # На завершении — корректно гасим все фоновые задачи.
        for task in background_tasks:
            task.cancel()
        for task in background_tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        logger.info("Background tasks stopped")


app = FastAPI(
    title="Solvix Chronometry — Edge API",
    version=__version__,
    description="Backend Edge-сервера системы хронометража.",
    lifespan=lifespan,
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(parts_router, prefix="/api/v1")
app.include_router(batches_router, prefix="/api/v1")
app.include_router(shifts_router, prefix="/api/v1")
app.include_router(badges_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(timelines_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(stations_router, prefix="/api/v1")
app.include_router(ws_router, prefix="/api/v1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/dashboard")
async def dashboard_redirect():
    return RedirectResponse(url="/static/dashboard.html")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": __version__, "env": settings.app_env}
