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
from solvix_chronometry.mqtt.subscriber import run_subscriber

# Без явного basicConfig uvicorn не пробрасывает наши INFO-логи в консоль
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # На старте: запускаем фоновый MQTT-подписчик
    subscriber_task = asyncio.create_task(run_subscriber(), name="mqtt-subscriber")
    logger.info("MQTT subscriber task started")

    try:
        yield
    finally:
        # На завершении: корректно гасим фоновый таск
        subscriber_task.cancel()
        try:
            await subscriber_task
        except asyncio.CancelledError:
            pass
        logger.info("MQTT subscriber task stopped")


app = FastAPI(
    title="Solvix Chronometry — Edge API",
    version=__version__,
    description="Backend Edge-сервера системы хронометража.",
    lifespan=lifespan,
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(ws_router, prefix="/api/v1")

# Demo: открытый CORS. На проде сузить allow_origins до реальных доменов фронтов.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Раздаём static/ как /static
app.mount("/static", StaticFiles(directory="static"), name="static")


# Демо-дашборд старшего по красивому URL
@app.get("/dashboard")
async def dashboard_redirect():
    return RedirectResponse(url="/static/dashboard.html")


@app.get("/health")
async def health() -> dict:
    """Простой healthcheck."""
    return {"status": "ok", "version": __version__, "env": settings.app_env}
