"""Детектор аномалии `norm_exceeded` — операция превысила норматив.

Алгоритм (по станкам):
1. Найти активный `start` (без последующего `stop`/`scan_out`).
2. Найти процесс для станка по `station_hint` (на пилоте — упрощение).
3. Посчитать длительность операции с вычетом пауз (закрытых и открытой).
4. Сравнить с `nominal_duration_sec * (1 + anomaly_threshold_pct/100)`.
5. Идемпотентность: проверить `details.start_event_id` среди anomaly-событий.
6. Создать `anomaly` если ещё не зафиксирована.

См. Обсидиан → Решения №62-63 (норматив и порог), №67 (учёт пауз).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.models.enums import EventType
from solvix_chronometry.models.events import Event
from solvix_chronometry.models.hierarchy import Station
from solvix_chronometry.models.processes import Process
from solvix_chronometry.watchdog.helpers import create_anomaly_event

logger = logging.getLogger(__name__)


async def detect_norm_exceeded(session: AsyncSession) -> int:
    """Обработать все станки. Вернуть количество созданных anomaly-событий."""
    now = datetime.now(timezone.utc)
    created = 0

    stations = (await session.execute(select(Station))).scalars().all()

    for station in stations:
        n = await _process_station(session, station, now)
        created += n

    return created


async def _process_station(session: AsyncSession, station: Station, now: datetime) -> int:
    # 1. Найти активный start.
    active_start = await _find_active_start(session, station.id)
    if active_start is None:
        return 0

    # 2. Найти процесс для станка.
    process = (await session.execute(
        select(Process)
        .where(Process.station_hint == station.id)
        .where(Process.valid_from <= now)
        .order_by(Process.valid_from.desc())
        .limit(1)
    )).scalar_one_or_none()
    if process is None:
        return 0

    # 3. Посчитать длительность с вычетом пауз.
    duration_sec = await _compute_active_duration(session, station.id, active_start.timestamp, now)
    threshold_sec = process.nominal_duration_sec * (1 + process.anomaly_threshold_pct / 100)

    if duration_sec <= threshold_sec:
        return 0

    # 4. Идемпотентность.
    if await _already_flagged(session, station.id, active_start):
        return 0

    # 5. Создаём.
    await create_anomaly_event(
        session,
        station_id=station.id,
        shift_id=active_start.shift_id,
        part_id=active_start.part_id,
        kind="norm_exceeded",
        details={
            "start_event_id": str(active_start.id),
            "duration_actual_sec": round(duration_sec, 1),
            "nominal_sec": process.nominal_duration_sec,
            "threshold_sec": round(threshold_sec, 1),
            "process_id": str(process.id),
        },
    )
    logger.info(
        "norm_exceeded on station %s: duration=%.0fs > threshold=%.0fs",
        station.name, duration_sec, threshold_sec,
    )
    return 1


async def _find_active_start(session: AsyncSession, station_id) -> Event | None:
    """Идём назад по событиям — первый `start` без `stop`/`scan_out` после него."""
    recent = (await session.execute(
        select(Event)
        .where(Event.station_id == station_id)
        .order_by(Event.timestamp.desc())
        .limit(50)
    )).scalars().all()

    for ev in recent:
        if ev.event_type == EventType.start:
            return ev
        if ev.event_type in (EventType.stop, EventType.scan_out):
            return None
    return None


async def _compute_active_duration(
    session: AsyncSession, station_id, start_ts: datetime, now: datetime,
) -> float:
    """Длительность от start до now минус суммарная пауза (закрытые + открытая)."""
    breaks = (await session.execute(
        select(Event)
        .where(Event.station_id == station_id)
        .where(Event.timestamp >= start_ts)
        .where(Event.event_type.in_([EventType.break_start, EventType.break_end]))
        .order_by(Event.timestamp.asc())
    )).scalars().all()

    total_pause = 0.0
    pending_start: datetime | None = None
    for b in breaks:
        if b.event_type == EventType.break_start:
            pending_start = b.timestamp
        elif b.event_type == EventType.break_end and pending_start is not None:
            total_pause += (b.timestamp - pending_start).total_seconds()
            pending_start = None

    if pending_start is not None:
        total_pause += (now - pending_start).total_seconds()

    return (now - start_ts).total_seconds() - total_pause


async def _already_flagged(session: AsyncSession, station_id, active_start: Event) -> bool:
    """Уже ли создана anomaly для этого конкретного start_event?"""
    anomalies = (await session.execute(
        select(Event)
        .where(Event.station_id == station_id)
        .where(Event.event_type == EventType.anomaly)
        .where(Event.timestamp >= active_start.timestamp)
    )).scalars().all()

    target = str(active_start.id)
    for a in anomalies:
        if a.details and a.details.get("kind") == "norm_exceeded" \
                and a.details.get("start_event_id") == target:
            return True
    return False
