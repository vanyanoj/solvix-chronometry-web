"""Таймлайны деталей и пользователей (supervisor-блок).

См. Обсидиан → Решение №84 (структура API).
"""
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.auth.dependencies import require_role
from solvix_chronometry.db import get_session
from solvix_chronometry.models.enums import EventType, UserRole
from solvix_chronometry.models.events import Event
from solvix_chronometry.models.hierarchy import Station
from solvix_chronometry.models.parts import Part
from solvix_chronometry.models.people import Shift, User

router = APIRouter(tags=["timelines"])


class TimelineEntry(BaseModel):
    """Одна запись в таймлайне."""
    id: UUID
    timestamp: datetime
    event_type: EventType
    station_id: UUID
    station_name: str
    shift_id: UUID | None = None
    part_id: str | None = None
    details: dict[str, Any] | None = None


# === GET /api/v1/parts/{part_id}/timeline ===

@router.get(
    "/parts/{part_id}/timeline",
    response_model=list[TimelineEntry],
    dependencies=[Depends(require_role(UserRole.supervisor))],
)
async def part_timeline(
    part_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[TimelineEntry]:
    """Все события связанные с конкретной деталью, в хронологическом порядке."""
    # Проверить что деталь существует
    part = (await session.execute(
        select(Part).where(Part.id == part_id)
    )).scalar_one_or_none()
    if part is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Part {part_id!r} not found",
        )

    # Достать события + станки одним запросом
    stmt = (
        select(Event, Station.name.label("station_name"))
        .outerjoin(Station, Event.station_id == Station.id)
        .where(Event.part_id == part_id)
        .order_by(Event.timestamp.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).all()

    return [
        TimelineEntry(
            id=ev.id,
            timestamp=ev.timestamp,
            event_type=ev.event_type,
            station_id=ev.station_id,
            station_name=station_name or "(deleted)",
            shift_id=ev.shift_id,
            part_id=ev.part_id,
            details=ev.details,
        )
        for ev, station_name in rows
    ]


# === GET /api/v1/users/{user_id}/timeline ===

@router.get(
    "/users/{user_id}/timeline",
    response_model=list[TimelineEntry],
    dependencies=[Depends(require_role(UserRole.supervisor))],
)
async def user_timeline(
    user_id: UUID,
    since: datetime | None = Query(default=None, description="ISO 8601, фильтр по timestamp >="),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[TimelineEntry]:
    """Все события связанные с пользователем через его смены, в хронологическом порядке."""
    # Проверить что юзер существует
    user = (await session.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    # Двойной JOIN: Event → Shift → проверить user_id; плюс Station для имени
    stmt = (
        select(Event, Station.name.label("station_name"))
        .join(Shift, Event.shift_id == Shift.id)
        .outerjoin(Station, Event.station_id == Station.id)
        .where(Shift.user_id == user_id)
    )
    if since is not None:
        stmt = stmt.where(Event.timestamp >= since)
    stmt = stmt.order_by(Event.timestamp.asc()).limit(limit).offset(offset)

    rows = (await session.execute(stmt)).all()

    return [
        TimelineEntry(
            id=ev.id,
            timestamp=ev.timestamp,
            event_type=ev.event_type,
            station_id=ev.station_id,
            station_name=station_name or "(deleted)",
            shift_id=ev.shift_id,
            part_id=ev.part_id,
            details=ev.details,
        )
        for ev, station_name in rows
    ]
