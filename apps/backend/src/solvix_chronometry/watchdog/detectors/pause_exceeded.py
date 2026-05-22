"""Детектор аномалии `pause_exceeded` — пауза превышает порог.

Алгоритм:
1. Найти все `break_start` за последние 8 часов.
2. Для каждого — проверить нет ли `break_end` после на той же станции.
3. Если открытая пауза — взять `reason_id` из `details`, найти BreakReason.
4. Сравнить возраст паузы с `max_duration_sec`.
5. Идемпотентность: `details.break_start_event_id`.

См. Обсидиан → Решения №68 (break_reasons как таблица), №69 (порог per причина).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.models.break_reasons import BreakReason
from solvix_chronometry.models.enums import EventType
from solvix_chronometry.models.events import Event
from solvix_chronometry.watchdog.helpers import create_anomaly_event

logger = logging.getLogger(__name__)

MAX_PAUSE_AGE_HOURS = 8  # верхняя граница — старше игнорируем (это уже station_idle)


async def detect_pause_exceeded(session: AsyncSession) -> int:
    """Обработать все открытые паузы. Вернуть количество созданных anomaly."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=MAX_PAUSE_AGE_HOURS)
    created = 0

    # Все break_start за окно (8 ч)
    break_starts = (await session.execute(
        select(Event)
        .where(Event.event_type == EventType.break_start)
        .where(Event.timestamp >= cutoff)
    )).scalars().all()

    for bs in break_starts:
        n = await _process_break_start(session, bs, now)
        created += n

    return created


async def _process_break_start(session: AsyncSession, bs: Event, now: datetime) -> int:
    # 1. Закрыта ли пауза?
    closed = (await session.execute(
        select(Event)
        .where(Event.station_id == bs.station_id)
        .where(Event.event_type == EventType.break_end)
        .where(Event.timestamp > bs.timestamp)
        .limit(1)
    )).scalar_one_or_none()
    if closed is not None:
        return 0

    # 2. Достать reason_id из details
    reason_id_raw = (bs.details or {}).get("reason_id")
    if not reason_id_raw:
        return 0

    try:
        reason_id = UUID(reason_id_raw) if isinstance(reason_id_raw, str) else reason_id_raw
    except (ValueError, TypeError):
        return 0

    # 3. Найти BreakReason
    reason = (await session.execute(
        select(BreakReason).where(BreakReason.id == reason_id)
    )).scalar_one_or_none()
    if reason is None:
        return 0

    # 4. Возраст vs порог
    duration_sec = (now - bs.timestamp).total_seconds()
    if duration_sec <= reason.max_duration_sec:
        return 0

    # 5. Идемпотентность
    if await _already_flagged(session, bs):
        return 0

    # 6. Создать аномалию
    await create_anomaly_event(
        session,
        station_id=bs.station_id,
        shift_id=bs.shift_id,
        kind="pause_exceeded",
        details={
            "break_start_event_id": str(bs.id),
            "reason_id": str(reason.id),
            "reason_code": reason.code,
            "duration_actual_sec": round(duration_sec, 1),
            "max_duration_sec": reason.max_duration_sec,
        },
    )
    logger.info(
        "pause_exceeded on station %s: reason=%s duration=%.0fs > max=%ds",
        bs.station_id, reason.code, duration_sec, reason.max_duration_sec,
    )
    return 1


async def _already_flagged(session: AsyncSession, bs: Event) -> bool:
    """Уже ли создана anomaly для этого конкретного break_start?"""
    anomalies = (await session.execute(
        select(Event)
        .where(Event.station_id == bs.station_id)
        .where(Event.event_type == EventType.anomaly)
        .where(Event.timestamp >= bs.timestamp)
    )).scalars().all()

    target = str(bs.id)
    for a in anomalies:
        if a.details and a.details.get("kind") == "pause_exceeded" \
                and a.details.get("break_start_event_id") == target:
            return True
    return False
