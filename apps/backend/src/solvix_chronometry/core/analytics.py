"""Аналитические расчёты (ядро).

Чистые вычислительные функции: принимают session + параметры,
возвращают простые структуры. HTTP-обвязка живёт в api/analytics.py.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.models.enums import EventType
from solvix_chronometry.models.events import Event
from solvix_chronometry.models.hierarchy import Station


def resolve_period(
    since: datetime | None, until: datetime | None,
) -> tuple[datetime, datetime]:
    """Дефолтный период аналитики — последние 7 дней."""
    now = datetime.now(timezone.utc)
    return since or (now - timedelta(days=7)), until or now


@dataclass(slots=True)
class ThroughputRow:
    station_id: UUID
    station_name: str
    period_start: datetime
    count: int


@dataclass(slots=True)
class AnomalySummaryRow:
    station_id: UUID
    station_name: str
    kind: str
    count: int


@dataclass(slots=True)
class CycleTimeRow:
    station_id: UUID
    station_name: str
    avg_sec: float
    median_sec: float
    min_sec: float
    max_sec: float
    count: int


async def compute_throughput(
    session: AsyncSession,
    since: datetime,
    until: datetime,
    group_by: str,
) -> list[ThroughputRow]:
    """Сколько деталей прошло через каждый станок за период (по scan_out)."""
    period_expr = func.date_trunc(group_by, Event.timestamp).label("period_start")
    stmt = (
        select(
            Event.station_id,
            Station.name.label("station_name"),
            period_expr,
            func.count().label("count"),
        )
        .join(Station, Station.id == Event.station_id)
        .where(Event.event_type == EventType.scan_out)
        .where(Event.timestamp >= since)
        .where(Event.timestamp < until)
        .group_by(Event.station_id, Station.name, period_expr)
        .order_by(period_expr, Station.name)
    )
    rows = (await session.execute(stmt)).all()
    return [
        ThroughputRow(
            station_id=r.station_id,
            station_name=r.station_name,
            period_start=r.period_start,
            count=r.count,
        )
        for r in rows
    ]


async def compute_anomaly_summary(
    session: AsyncSession,
    since: datetime,
    until: datetime,
) -> list[AnomalySummaryRow]:
    """Сводка аномалий: сколько каких видов на каких станках за период."""
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
        .where(Event.timestamp >= since)
        .where(Event.timestamp < until)
        .group_by(Event.station_id, Station.name, kind_expr)
        .order_by(Station.name, func.count().desc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        AnomalySummaryRow(
            station_id=r.station_id,
            station_name=r.station_name,
            kind=r.kind or "unknown",
            count=r.count,
        )
        for r in rows
    ]


async def compute_cycle_times(
    session: AsyncSession,
    since: datetime,
    until: datetime,
) -> list[CycleTimeRow]:
    """Времена циклов операций (start → stop) по станкам.

    avg/median/min/max длительности для каждого станка.
    На пилоте — без вычета пауз внутри операции (упрощение).
    """
    stmt = (
        select(Event.station_id, Event.timestamp, Event.event_type)
        .where(Event.event_type.in_([EventType.start, EventType.stop]))
        .where(Event.timestamp >= since)
        .where(Event.timestamp < until)
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

    stations = (await session.execute(
        select(Station).where(Station.id.in_(list(station_durations.keys())))
    )).scalars().all()
    names = {s.id: s.name for s in stations}

    results: list[CycleTimeRow] = []
    for station_id, durations in station_durations.items():
        durations_sorted = sorted(durations)
        n = len(durations_sorted)
        median = (
            durations_sorted[n // 2] if n % 2 == 1
            else (durations_sorted[n // 2 - 1] + durations_sorted[n // 2]) / 2
        )
        results.append(CycleTimeRow(
            station_id=station_id,
            station_name=names.get(station_id, "(deleted)"),
            avg_sec=round(sum(durations) / n, 2),
            median_sec=round(median, 2),
            min_sec=round(min(durations), 2),
            max_sec=round(max(durations), 2),
            count=n,
        ))

    results.sort(key=lambda x: x.station_name)
    return results
