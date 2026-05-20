"""FastAPI-приложение Edge-сервера."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from solvix_chronometry import __version__
from solvix_chronometry.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # На старте: проверки, прогрев и т.п. Пока пусто.
    yield
    # На завершении: graceful shutdown — закрытие пулов, MQTT-клиента и т.п.


app = FastAPI(
    title="Solvix Chronometry — Edge API",
    version=__version__,
    description="Backend Edge-сервера системы хронометража.",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict:
    """Простой healthcheck."""
    return {"status": "ok", "version": __version__, "env": settings.app_env}
