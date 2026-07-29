"""Lines endpoints — линии как сборочные потоки (Решение №85).

Линия = сборочный поток = изделие. Экран «Обзор» — список линий,
клик по строке открывает пирамиду (`GET /processes/topology/{line_id}`).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.auth.dependencies import require_role
from solvix_chronometry.db import get_session
from solvix_chronometry.models.enums import UserRole
from solvix_chronometry.models.hierarchy import Line, Station
from solvix_chronometry.models.people import Shift
from solvix_chronometry.models.processes import Process

router = APIRouter(prefix="/lines", tags=["lines"])


class LineResponse(BaseModel):
    """Линия + сводка для строки списка на «Обзоре»."""

    id: UUID
    workshop_id: UUID
    name: str
    #: сколько станков на линии
    station_count: int
    #: сколько станков занято прямо сейчас (есть активная смена)
    active_station_count: int
    #: сколько операций заведено в справочнике
    process_count: int
    #: топология построена (есть хотя бы одна операция со станком)
    has_topology: bool


@router.get(
    "",
    response_model=list[LineResponse],
    dependencies=[Depends(require_role(UserRole.supervisor))],
)
async def list_lines(
    workshop_id: UUID | None = Query(default=None, description="Фильтр по цеху"),
    session: AsyncSession = Depends(get_session),
) -> list[LineResponse]:
    """Список линий со сводкой. На пилоте — одна линия."""
    query = select(Line)
    if workshop_id is not None:
        query = query.where(Line.workshop_id == workshop_id)
    lines = list((await session.execute(query.order_by(Line.name))).scalars().all())
    if not lines:
        return []

    line_ids = [line.id for line in lines]

    # Станки по линиям.
    station_rows = (
        await session.execute(
            select(Station.line_id, func.count(Station.id))
            .where(Station.line_id.in_(line_ids))
            .group_by(Station.line_id)
        )
    ).all()
    stations_by_line = {lid: cnt for lid, cnt in station_rows}

    # Занятые станки: активная смена = unbound_at IS NULL.
    active_rows = (
        await session.execute(
            select(Station.line_id, func.count(func.distinct(Shift.station_id)))
            .join(Shift, Shift.station_id == Station.id)
            .where(Station.line_id.in_(line_ids))
            .where(Shift.unbound_at.is_(None))
            .group_by(Station.line_id)
        )
    ).all()
    active_by_line = {lid: cnt for lid, cnt in active_rows}

    # Операции в справочнике.
    process_rows = (
        await session.execute(
            select(Process.line_id, func.count(Process.id))
            .where(Process.line_id.in_(line_ids))
            .group_by(Process.line_id)
        )
    ).all()
    processes_by_line = {lid: cnt for lid, cnt in process_rows}

    # Линии, где есть хотя бы одна операция с указанным станком.
    topo_rows = (
        await session.execute(
            select(Process.line_id)
            .where(Process.line_id.in_(line_ids))
            .where(Process.station_hint.is_not(None))
            .distinct()
        )
    ).all()
    lines_with_topology = {row[0] for row in topo_rows}

    return [
        LineResponse(
            id=line.id,
            workshop_id=line.workshop_id,
            name=line.name,
            station_count=stations_by_line.get(line.id, 0),
            active_station_count=active_by_line.get(line.id, 0),
            process_count=processes_by_line.get(line.id, 0),
            has_topology=line.id in lines_with_topology,
        )
        for line in lines
    ]


@router.get(
    "/{line_id}",
    response_model=LineResponse,
    dependencies=[Depends(require_role(UserRole.supervisor))],
)
async def get_line(
    line_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> LineResponse:
    """Одна линия со сводкой."""
    line = (
        await session.execute(select(Line).where(Line.id == line_id))
    ).scalar_one_or_none()
    if line is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Line {line_id} not found")

    station_count = (
        await session.execute(
            select(func.count(Station.id)).where(Station.line_id == line_id)
        )
    ).scalar_one()

    active_count = (
        await session.execute(
            select(func.count(func.distinct(Shift.station_id)))
            .join(Station, Shift.station_id == Station.id)
            .where(Station.line_id == line_id)
            .where(Shift.unbound_at.is_(None))
        )
    ).scalar_one()

    process_count = (
        await session.execute(
            select(func.count(Process.id)).where(Process.line_id == line_id)
        )
    ).scalar_one()

    with_station = (
        await session.execute(
            select(func.count(Process.id))
            .where(Process.line_id == line_id)
            .where(Process.station_hint.is_not(None))
        )
    ).scalar_one()

    return LineResponse(
        id=line.id,
        workshop_id=line.workshop_id,
        name=line.name,
        station_count=station_count,
        active_station_count=active_count,
        process_count=process_count,
        has_topology=with_station > 0,
    )
