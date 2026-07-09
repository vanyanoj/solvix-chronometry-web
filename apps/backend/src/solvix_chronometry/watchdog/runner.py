"""Watchdog runner — фоновый async-loop детекции аномалий."""
from __future__ import annotations

import asyncio
import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.db import SessionLocal
from solvix_chronometry.core.detectors import detect_norm_exceeded, detect_pause_exceeded, detect_station_idle, detect_transit_stuck

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 5 if os.getenv("WATCHDOG_DEMO_MODE") == "1" else 30


async def run_watchdog() -> None:
    """Главный цикл watchdog. Стартует из FastAPI lifespan."""
    logger.info("Watchdog started (poll interval: %d sec)", POLL_INTERVAL_SEC)

    iteration = 0
    try:
        while True:
            iteration += 1
            try:
                async with SessionLocal() as session:
                    anomalies = await _run_detectors(session)
                    if anomalies > 0:
                        await session.commit()
                        logger.info("Watchdog iter %d: created %d anomaly events", iteration, anomalies)
            except Exception:
                logger.exception("Watchdog iter %d failed", iteration)

            await asyncio.sleep(POLL_INTERVAL_SEC)
    except asyncio.CancelledError:
        logger.info("Watchdog cancelled (graceful shutdown)")
        raise


async def _run_detectors(session: AsyncSession) -> int:
    """Прогнать все детекторы. Возвращает суммарное число anomaly-событий."""
    count = 0
    count += await detect_norm_exceeded(session)
    count += await detect_pause_exceeded(session)
    count += await detect_station_idle(session)
    count += await detect_transit_stuck(session)
    return count
