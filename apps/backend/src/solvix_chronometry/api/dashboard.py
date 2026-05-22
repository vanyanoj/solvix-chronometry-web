"""Dashboard endpoints — данные для главного экрана старшего цеха.

API-контракт — Обсидиан → Решения №71-75 (UI старшего) и №84 (структура API).
"""
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.auth.dependencies import require_role
from solvix_chronometry.db import get_session
from solvix_chronometry.models.enums import EventType, UserRole
from solvix_chronometry.models.events import Event
from solvix_chronometry.models.hierarchy import Station
from solvix_chronometry.models.people import Shift, User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# === Response schemas ===

class OperatorSnapshot(BaseModel):
    id: UUID
    full_name: str


class LastEventSnapshot(BaseModel):
    type: str
    at: datetime
    part_id: str | None = None


class StationSnapshot(BaseModel):
    id: UUID
    name: str
    operator: OperatorSnapshot | None = None
    active_shift_id: UUID | None = None
    last_event: LastEventSnapshot | None = None


class IncidentItem(BaseModel):
    """Один инцидент в ленте старшего — событие типа anomaly или error."""
    id: UUID
    timestamp: datetime
    event_type: EventType
    station_id: UUID
    station_name: str
    part_id: str | None = None
    shift_id: UUID | None = None
    details: dict[str, Any] | None = None


# === GET /dashboard/stations (без auth — для HTML-демки) ===

@router.get("/stations", response_model=list[StationSnapshot])
async def get_dashboard_stations(
    session: AsyncSession = Depends(get_session),
) -> list[StationSnapshot]:
    """Снимок состояния всех станков для главного экрана."""
    stations = (await session.execute(select(Station))).scalars().all()

    result: list[StationSnapshot] = []
    for station in stations:
        shift = (await session.execute(
            select(Shift)
            .where(Shift.station_id == station.id)
            .where(Shift.unbound_at.is_(None))
            .order_by(Shift.bound_at.desc())
            .limit(1)
        )).scalar_one_or_none()

        operator: OperatorSnapshot | None = None
        active_shift_id: UUID | None = None
        if shift is not None:
            active_shift_id = shift.id
            user = (await session.execute(
                select(User).where(User.id == shift.user_id)
            )).scalar_one_or_none()
            if user is not None:
                operator = OperatorSnapshot(id=user.id, full_name=user.full_name)

        event = (await session.execute(
            select(Event)
            .where(Event.station_id == station.id)
            .order_by(Event.timestamp.desc())
            .limit(1)
        )).scalar_one_or_none()

        last_event: LastEventSnapshot | None = None
        if event is not None:
            event_type_str = getattr(event.event_type, "value", str(event.event_type))
            last_event = LastEventSnapshot(type=event_type_str, at=event.timestamp, part_id=event.part_id)

        result.append(StationSnapshot(
            id=station.id,
            name=station.name,
            operator=operator,
            active_shift_id=active_shift_id,
            last_event=last_event,
        ))

    return result


# === GET /dashboard/incidents (supervisor auth) ===

@router.get(
    "/incidents",
    response_model=list[IncidentItem],
    dependencies=[Depends(require_role(UserRole.supervisor))],
)
async def list_incidents(
    since: datetime | None = Query(
        default=None,
        description="С какого момента (ISO 8601). По умолчанию — последние 8 часов (одна смена).",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[IncidentItem]:
    """Лента инцидентов за период — события типа `anomaly` и `error`.

    Используется во вкладке старшего как лента «что было за смену» (Решение №71).
    Сортировка: свежие сверху (timestamp DESC).
    """
    if since is None:
        since = datetime.now(timezone.utc) - timedelta(hours=8)

    stmt = (
        select(Event, Station.name.label("station_name"))
        .outerjoin(Station, Event.station_id == Station.id)
        .where(Event.event_type.in_([EventType.anomaly, EventType.error]))
        .where(Event.timestamp >= since)
        .order_by(Event.timestamp.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).all()

    return [
        IncidentItem(
            id=ev.id,
            timestamp=ev.timestamp,
            event_type=ev.event_type,
            station_id=ev.station_id,
            station_name=station_name or "(deleted)",
            part_id=ev.part_id,
            shift_id=ev.shift_id,
            details=ev.details,
        )
        for ev, station_name in rows
    ]
