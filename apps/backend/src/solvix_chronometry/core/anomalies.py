"""Хелперы для watchdog-детекторов."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.models.enums import EventType
from solvix_chronometry.models.events import Event


async def create_anomaly_event(
    session: AsyncSession,
    *,
    station_id: UUID,
    kind: str,
    details: dict[str, Any] | None = None,
    shift_id: UUID | None = None,
    part_id: str | None = None,
    timestamp: datetime | None = None,
) -> Event:
    """Создать event типа `anomaly` с заданным `details.kind`.

    Используется детекторами watchdog. UUID v7 для `id` генерится автоматически.
    Caller сам решает когда коммитить session.

    Args:
        session: активная сессия БД (caller сам коммитит).
        station_id: на каком станке зафиксирована аномалия.
        kind: вид аномалии — записывается в `details.kind`.
              Допустимо: `norm_exceeded` / `transit_stuck` / `pause_exceeded` / `station_idle`.
        details: доп. поля (длительности, нормативы). Сливаются с `kind`.
        shift_id: какая смена активна (nullable).
        part_id: какая деталь связана (nullable).
        timestamp: время аномалии (default = now).

    Returns:
        Созданный (добавленный в session, но НЕ закомиченный) Event.
    """
    now = timestamp or datetime.now(timezone.utc)
    full_details = {"kind": kind, **(details or {})}
    event = Event(
        timestamp=now,
        received_at=now,
        station_id=station_id,
        shift_id=shift_id,
        event_type=EventType.anomaly,
        part_id=part_id,
        details=full_details,
    )
    session.add(event)
    return event
