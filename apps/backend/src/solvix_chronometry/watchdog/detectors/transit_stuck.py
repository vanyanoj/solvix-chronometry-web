"""Детектор аномалии `transit_stuck` — деталь застряла в транзите.

Алгоритм (упрощённо на пилоте, без топологии):
1. Найти `scan_out` события за последние 2 часа с непустым part_id.
2. Для каждого — проверить нет ли `scan_in` с тем же part_id ПОСЛЕ него на любом станке.
3. Если нет и прошло > порога → создать `anomaly`.
4. Идемпотентность: `details.scan_out_event_id`.

См. Обсидиан → Решения №65-66 (транзит и зависание).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.models.enums import EventType
from solvix_chronometry.models.events import Event
from solvix_chronometry.watchdog.helpers import create_anomaly_event

logger = logging.getLogger(__name__)

TRANSIT_STUCK_THRESHOLD_SEC = 30 if os.getenv("WATCHDOG_DEMO_MODE") == "1" else 5 * 60  # 30 сек в демо, 5 мин на проде
MAX_TRANSIT_AGE_HOURS = 2


async def detect_transit_stuck(session: AsyncSession) -> int:
    """Обработать все scan_out за окно. Вернуть число anomaly."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=MAX_TRANSIT_AGE_HOURS)
    created = 0

    scan_outs = (await session.execute(
        select(Event)
        .where(Event.event_type == EventType.scan_out)
        .where(Event.timestamp >= cutoff)
        .where(Event.part_id.is_not(None))
    )).scalars().all()

    for so in scan_outs:
        n = await _process_scan_out(session, so, now)
        created += n

    return created


async def _process_scan_out(session: AsyncSession, so: Event, now: datetime) -> int:
    # 1. Прошло ли достаточно времени?
    age_sec = (now - so.timestamp).total_seconds()
    if age_sec <= TRANSIT_STUCK_THRESHOLD_SEC:
        return 0

    # 2. Был ли scan_in с тем же part_id?
    scan_in = (await session.execute(
        select(Event)
        .where(Event.event_type == EventType.scan_in)
        .where(Event.part_id == so.part_id)
        .where(Event.timestamp > so.timestamp)
        .limit(1)
    )).scalar_one_or_none()
    if scan_in is not None:
        return 0

    # 3. Идемпотентность.
    if await _already_flagged(session, so):
        return 0

    # 4. Создать аномалию.
    await create_anomaly_event(
        session,
        station_id=so.station_id,
        shift_id=so.shift_id,
        part_id=so.part_id,
        kind="transit_stuck",
        details={
            "scan_out_event_id": str(so.id),
            "scan_out_station_id": str(so.station_id),
            "duration_actual_sec": round(age_sec, 1),
            "threshold_sec": TRANSIT_STUCK_THRESHOLD_SEC,
        },
    )
    logger.info(
        "transit_stuck: part=%s scan_out from station=%s stuck for %.0fs",
        so.part_id, so.station_id, age_sec,
    )
    return 1


async def _already_flagged(session: AsyncSession, so: Event) -> bool:
    """Уже ли отмечено для этого scan_out?"""
    anomalies = (await session.execute(
        select(Event)
        .where(Event.event_type == EventType.anomaly)
        .where(Event.part_id == so.part_id)
        .where(Event.timestamp >= so.timestamp)
    )).scalars().all()
    target = str(so.id)
    for a in anomalies:
        if a.details and a.details.get("kind") == "transit_stuck" \
                and a.details.get("scan_out_event_id") == target:
            return True
    return False
