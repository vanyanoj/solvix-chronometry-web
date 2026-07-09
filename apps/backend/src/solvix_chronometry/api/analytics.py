"""Аналитика по производству (supervisor-блок) — HTTP-обвязка.

Расчёты живут в core.analytics (компилируемое ядро).
См. Обсидиан → Решение №84 (структура API).
"""
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.auth.dependencies import require_role
from solvix_chronometry.core import analytics as core_analytics
from solvix_chronometry.db import get_session
from solvix_chronometry.models.enums import UserRole

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
    since_ts, until_ts = core_analytics.resolve_period(since, until)
    rows = await core_analytics.compute_throughput(session, since_ts, until_ts, group_by.value)
    return [ThroughputItem(**asdict(row)) for row in rows]


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
    since_ts, until_ts = core_analytics.resolve_period(since, until)
    rows = await core_analytics.compute_anomaly_summary(session, since_ts, until_ts)
    return [AnomalySummaryItem(**asdict(row)) for row in rows]


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
    """Времена циклов операций (start → stop) по станкам."""
    since_ts, until_ts = core_analytics.resolve_period(since, until)
    rows = await core_analytics.compute_cycle_times(session, since_ts, until_ts)
    return [CycleTimeItem(**asdict(row)) for row in rows]
