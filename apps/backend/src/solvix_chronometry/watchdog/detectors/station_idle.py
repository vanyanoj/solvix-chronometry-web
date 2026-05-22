"""Детектор аномалии `station_idle` — активная смена без событий N минут.

Алгоритм:
1. Найти активные смены (unbound_at IS NULL, station_id привязан).
2. Для каждой — найти последнее событие на станке после `bound_at`.
3. Если последнее = `start` или `break_start` — пропустить (это работа/пауза, не idle).
4. Если простой > порога → создать `anomaly`.
5. Идемпотентность: по `shift_id` + `details.idle_since`.

См. Обсидиан → Решение №70 (станок простаивает при активной смене).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.models.enums import EventType
from solvix_chronometry.models.events import Event
from solvix_chronometry.models.people import Shift
from solvix_chronometry.watchdog.helpers import create_anomaly_event

logger = logging.getLogger(__name__)

STATION_IDLE_THRESHOLD_SEC = 15 * 60  # 15 минут — пороже простоя


async def detect_station_idle(session: AsyncSession) -> int:
    """Обработать все активные смены. Вернуть количество созданных anomaly."""
    now = datetime.now(timezone.utc)
    created = 0

    active_shifts = (await session.execute(
        select(Shift)
        .where(Shift.unbound_at.is_(None))
        .where(Shift.station_id.is_not(None))
    )).scalars().all()

    for shift in active_shifts:
        n = await _process_shift(session, shift, now)
        created += n

    return created


async def _process_shift(session: AsyncSession, shift: Shift, now: datetime) -> int:
    # 1. Последнее событие на станке после начала смены.
    last_event = (await session.execute(
        select(Event)
        .where(Event.station_id == shift.station_id)
        .where(Event.timestamp >= shift.bound_at)
        .order_by(Event.timestamp.desc())
        .limit(1)
    )).scalar_one_or_none()

    # 2. Если последнее = start или break_start — это активная работа/пауза, не idle.
    if last_event is not None and last_event.event_type in (
        EventType.start, EventType.break_start,
    ):
        return 0

    # 3. Считаем простой: от последнего события (или от bound_at если событий нет).
    idle_since = last_event.timestamp if last_event else shift.bound_at
    idle_sec = (now - idle_since).total_seconds()
    if idle_sec <= STATION_IDLE_THRESHOLD_SEC:
        return 0

    # 4. Идемпотентность: фильтр по shift_id и idle_since.
    idle_since_iso = idle_since.isoformat()
    existing = (await session.execute(
        select(Event)
        .where(Event.shift_id == shift.id)
        .where(Event.event_type == EventType.anomaly)
    )).scalars().all()

    already = any(
        a.details and a.details.get("kind") == "station_idle"
        and a.details.get("idle_since") == idle_since_iso
        for a in existing
    )
    if already:
        return 0

    # 5. Создать аномалию.
    await create_anomaly_event(
        session,
        station_id=shift.station_id,
        shift_id=shift.id,
        kind="station_idle",
        details={
            "last_event_id": str(last_event.id) if last_event else None,
            "idle_since": idle_since_iso,
            "duration_actual_sec": round(idle_sec, 1),
            "threshold_sec": STATION_IDLE_THRESHOLD_SEC,
        },
    )
    logger.info(
        "station_idle on station %s (shift %s): idle for %.0f sec",
        shift.station_id, shift.id, idle_sec,
    )
    return 1
