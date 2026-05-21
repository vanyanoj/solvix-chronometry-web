"""Dashboard endpoints — данные для главного экрана старшего цеха.

API-контракт — Обсидиан → Решения №71-75 (UI старшего) и №84 (структура API).
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.db import get_session
from solvix_chronometry.models.events import Event
from solvix_chronometry.models.hierarchy import Station
from solvix_chronometry.models.people import Shift, User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# === Response schemas ===

class OperatorSnapshot(BaseModel):
    """Текущий оператор станка."""
    id: UUID
    full_name: str


class LastEventSnapshot(BaseModel):
    """Последнее зафиксированное событие на станке."""
    type: str
    at: datetime
    part_id: str | None = None


class StationSnapshot(BaseModel):
    """Снимок состояния одного станка для главного экрана."""
    id: UUID
    name: str
    operator: OperatorSnapshot | None = None
    active_shift_id: UUID | None = None
    last_event: LastEventSnapshot | None = None


# === Endpoint ===

@router.get("/stations", response_model=list[StationSnapshot])
async def get_dashboard_stations(
    session: AsyncSession = Depends(get_session),
) -> list[StationSnapshot]:
    """Snapshot всех станков для главного экрана старшего.

    Для каждого станка возвращает: имя, текущего оператора (если есть активная
    смена), последнее зафиксированное событие. Этого достаточно чтобы отрисовать
    4 карточки на главном (Решения №71-75).

    Поле online (онлайн-статус терминала) пока не считается — оно требует
    MQTT state-топика (Решение №79), реализуем позже.
    """
    stations = (await session.execute(select(Station))).scalars().all()

    result: list[StationSnapshot] = []
    for station in stations:
        # Активная смена на этом станке (unbound_at IS NULL = ещё открыта)
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

        # Последнее событие на этом станке
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
