"""Аналитика по производству (supervisor-блок).

См. Обсидиан → Решение №84 (структура API).
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.auth.dependencies import require_role
from solvix_chronometry.db import get_session
from solvix_chronometry.models.enums import EventType, UserRole
from solvix_chronometry.models.events import Event
from solvix_chronometry.models.hierarchy import Station

router = APIRouter(prefix="/analytics", tags=["analytics"])


class GroupBy(str, Enum):
    hour = "hour"
    day = "day"
    week = "week"


# === Schemas ===

class ThroughputItem(BaseModel):
    station_id: UUID
    station_name: str
    period_start: datetime
    count: int


class AnomalySummaryItem(BaseModel):
    kind: str
    station_id: UUID
    station_name: str
    count: int


class CycleTimeItem(BaseModel):
    station_id: UUID
    station_name: str
    avg_sec: float
    median_sec: float
    min_sec: float
    max_sec: float
    count: int


def _resolve_period(since: datetime | None, until: datetime | None) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    return since or (now - timedelta(days=7)), until or now


# === GET /analytics/throughput ===

@router.get(
    "/throughput",
    response_model=list[ThroughputItem],
    dependencies=[Depends(require_role(UserRole.supervisor))],
)
async def throughput(
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    group_by: GroupBy = Query(default=GroupBy.day),
    session: AsyncSession = Depends(get_session),
) -> list[ThroughputItem]:
    """Сколько деталей прошло через каждый станок за период (по scan_out)."""
    since_ts, until_ts = _resolve_period(since, until)

    period_expr = func.date_trunc(group_by.value, Event.timestamp).label("period_start")
    stmt = (
        select(
            Event.station_id,
            Station.name.label("station_name"),
            period_expr,
            func.count().label("count"),
        )
        .join(Station, Station.id == Event.station_id)
        .where(Event.event_type == EventType.scan_out)
        .where(Event.timestamp >= since_ts)
        .where(Event.timestamp < until_ts)
        .group_by(Event.station_id, Station.name, period_expr)
        .order_by(period_expr, Station.name)
    )
    rows = (await session.execute(stmt)).all()

    return [
        ThroughputItem(
            station_id=r.station_id,
            station_name=r.station_name,
            period_start=r.period_start,
            count=r.count,
        )
        for r in rows
    ]


# === GET /analytics/anomalies ===

@router.get(
    "/anomalies",
    response_model=list[AnomalySummaryItem],
    dependencies=[Depends(require_role(UserRole.supervisor))],
)
async def anomalies(
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[AnomalySummaryItem]:
    """Сводка аномалий: сколько каких видов на каких станках за период."""
    since_ts, until_ts = _resolve_period(since, until)

    kind_expr = Event.details["kind"].astext.label("kind")
    stmt = (
        select(
            Event.station_id,
            Station.name.label("station_name"),
            kind_expr,
            func.count().label("count"),
        )
        .join(Station, Station.id == Event.station_id)
        .where(Event.event_type == EventType.anomaly)
        .where(Event.timestamp >= since_ts)
        .where(Event.timestamp < until_ts)
        .group_by(Event.station_id, Station.name, kind_expr)
        .order_by(Station.name, func.count().desc())
    )
    rows = (await session.execute(stmt)).all()

    return [
        AnomalySummaryItem(
            station_id=r.station_id,
            station_name=r.station_name,
            kind=r.kind or "unknown",
            count=r.count,
        )
        for r in rows
    ]


# === GET /analytics/cycle_times ===

@router.get(
    "/cycle_times",
    response_model=list[CycleTimeItem],
    dependencies=[Depends(require_role(UserRole.supervisor))],
)
async def cycle_times(
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[CycleTimeItem]:
    """Времена циклов операций (start → stop) по станкам.

    Возвращает avg/median/min/max длительности для каждого станка.
    На пилоте — без вычета пауз внутри операции (упрощение).
    """
    since_ts, until_ts = _resolve_period(since, until)

    stmt = (
        select(Event.station_id, Event.timestamp, Event.event_type)
        .where(Event.event_type.in_([EventType.start, EventType.stop]))
        .where(Event.timestamp >= since_ts)
        .where(Event.timestamp < until_ts)
        .order_by(Event.station_id, Event.timestamp)
    )
    rows = (await session.execute(stmt)).all()

    # Сшиваем пары start → stop на каждой станции
    station_durations: dict[UUID, list[float]] = defaultdict(list)
    station_last_start: dict[UUID, datetime] = {}

    for row in rows:
        if row.event_type == EventType.start:
            station_last_start[row.station_id] = row.timestamp
        elif row.event_type == EventType.stop:
            start_ts = station_last_start.pop(row.station_id, None)
            if start_ts is not None:
                station_durations[row.station_id].append(
                    (row.timestamp - start_ts).total_seconds()
                )

    if not station_durations:
        return []

    # Берём имена станций
    stations = (await session.execute(
        select(Station).where(Station.id.in_(list(station_durations.keys())))
    )).scalars().all()
    names = {s.id: s.name for s in stations}

    results: list[CycleTimeItem] = []
    for station_id, durations in station_durations.items():
        durations_sorted = sorted(durations)
        n = len(durations_sorted)
        median = (
            durations_sorted[n // 2] if n % 2 == 1
            else (durations_sorted[n // 2 - 1] + durations_sorted[n // 2]) / 2
        )
        results.append(CycleTimeItem(
            station_id=station_id,
            station_name=names.get(station_id, "(deleted)"),
            avg_sec=round(sum(durations) / n, 2),
            median_sec=round(median, 2),
            min_sec=round(min(durations), 2),
            max_sec=round(max(durations), 2),
            count=n,
        ))

    # Стабильный порядок — по имени
    results.sort(key=lambda x: x.station_name)
    return results
