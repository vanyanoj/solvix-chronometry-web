"""Тесты analytics-эндпоинтов (supervisor-блок)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from solvix_chronometry.db import SessionLocal
from solvix_chronometry.models.enums import EventType
from solvix_chronometry.models.events import Event
from solvix_chronometry.models.hierarchy import Line, Station


@pytest_asyncio.fixture
async def temp_station() -> AsyncIterator[Station]:
    sid: UUID | None = None
    try:
        async with SessionLocal() as session:
            line = (await session.execute(select(Line).limit(1))).scalar_one_or_none()
            if line is None:
                raise RuntimeError("Нет Line в БД.")
            unique = uuid4().hex[:8]
            st = Station(
                line_id=line.id,
                name=f"AnalyticsTest-{unique[:6]}",
                terminal_mac=f"02:{unique[0:2]}:{unique[2:4]}:{unique[4:6]}:22:22",
            )
            session.add(st)
            await session.commit()
            await session.refresh(st)
            sid = st.id
        async with SessionLocal() as session:
            yield (await session.execute(select(Station).where(Station.id == sid))).scalar_one()
    finally:
        if sid:
            async with SessionLocal() as session:
                async with session.begin():
                    await session.execute(delete(Event).where(Event.station_id == sid))
                    await session.execute(delete(Station).where(Station.id == sid))


async def _add(
    station_id: UUID, event_type: EventType, ts: datetime,
    part_id: str | None = None, details: dict | None = None,
) -> UUID:
    async with SessionLocal() as session:
        ev = Event(
            timestamp=ts, received_at=ts,
            station_id=station_id, event_type=event_type,
            part_id=part_id, details=details,
        )
        session.add(ev)
        await session.commit()
        await session.refresh(ev)
        return ev.id


# === THROUGHPUT ===

async def test_throughput_no_token_returns_401(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/analytics/throughput")).status_code == 401


async def test_throughput_warehouse_forbidden(warehouse_client: AsyncClient) -> None:
    assert (await warehouse_client.get("/api/v1/analytics/throughput")).status_code == 403


async def test_throughput_basic_returns_200(supervisor_client: AsyncClient) -> None:
    r = await supervisor_client.get("/api/v1/analytics/throughput")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_throughput_invalid_group_by(supervisor_client: AsyncClient) -> None:
    r = await supervisor_client.get("/api/v1/analytics/throughput?group_by=year")
    assert r.status_code == 422


async def test_throughput_counts_scan_outs(
    supervisor_client: AsyncClient, temp_station: Station,
) -> None:
    """3 scan_out за последний час → count=3 для нашей станции."""
    now = datetime.now(timezone.utc)
    for i in range(3):
        await _add(temp_station.id, EventType.scan_out, now - timedelta(minutes=i * 5))
    # Один scan_in не должен попасть в throughput
    await _add(temp_station.id, EventType.scan_in, now)

    r = await supervisor_client.get(
        "/api/v1/analytics/throughput",
        params={"since": (now - timedelta(hours=1)).isoformat(), "group_by": "day"},
    )
    assert r.status_code == 200
    our = [it for it in r.json() if it["station_id"] == str(temp_station.id)]
    assert len(our) == 1
    assert our[0]["count"] == 3
    assert our[0]["station_name"] == temp_station.name


# === ANOMALIES ===

async def test_anomalies_no_token_returns_401(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/analytics/anomalies")).status_code == 401


async def test_anomalies_warehouse_forbidden(warehouse_client: AsyncClient) -> None:
    assert (await warehouse_client.get("/api/v1/analytics/anomalies")).status_code == 403


async def test_anomalies_basic_returns_200(supervisor_client: AsyncClient) -> None:
    r = await supervisor_client.get("/api/v1/analytics/anomalies")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_anomalies_groups_by_kind(
    supervisor_client: AsyncClient, temp_station: Station,
) -> None:
    """2 norm_exceeded + 1 pause_exceeded на одной станции → 2 строки в ответе."""
    now = datetime.now(timezone.utc)
    await _add(temp_station.id, EventType.anomaly, now - timedelta(minutes=10),
               details={"kind": "norm_exceeded", "duration_actual_sec": 50})
    await _add(temp_station.id, EventType.anomaly, now - timedelta(minutes=20),
               details={"kind": "norm_exceeded", "duration_actual_sec": 60})
    await _add(temp_station.id, EventType.anomaly, now - timedelta(minutes=30),
               details={"kind": "pause_exceeded", "duration_actual_sec": 200})

    r = await supervisor_client.get(
        "/api/v1/analytics/anomalies",
        params={"since": (now - timedelta(hours=1)).isoformat()},
    )
    assert r.status_code == 200
    our = [it for it in r.json() if it["station_id"] == str(temp_station.id)]
    by_kind = {it["kind"]: it["count"] for it in our}
    assert by_kind.get("norm_exceeded") == 2
    assert by_kind.get("pause_exceeded") == 1


# === CYCLE TIMES ===

async def test_cycle_times_no_token_returns_401(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/analytics/cycle_times")).status_code == 401


async def test_cycle_times_warehouse_forbidden(warehouse_client: AsyncClient) -> None:
    assert (await warehouse_client.get("/api/v1/analytics/cycle_times")).status_code == 403


async def test_cycle_times_basic_returns_200(supervisor_client: AsyncClient) -> None:
    r = await supervisor_client.get("/api/v1/analytics/cycle_times")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_cycle_times_pairs_start_stop(
    supervisor_client: AsyncClient, temp_station: Station,
) -> None:
    """3 пары start/stop → avg/median/min/max посчитаны корректно."""
    now = datetime.now(timezone.utc)
    # Цикл 1: 10 сек
    await _add(temp_station.id, EventType.start, now - timedelta(minutes=30, seconds=10))
    await _add(temp_station.id, EventType.stop, now - timedelta(minutes=30))
    # Цикл 2: 20 сек
    await _add(temp_station.id, EventType.start, now - timedelta(minutes=20, seconds=20))
    await _add(temp_station.id, EventType.stop, now - timedelta(minutes=20))
    # Цикл 3: 30 сек
    await _add(temp_station.id, EventType.start, now - timedelta(minutes=10, seconds=30))
    await _add(temp_station.id, EventType.stop, now - timedelta(minutes=10))

    r = await supervisor_client.get(
        "/api/v1/analytics/cycle_times",
        params={"since": (now - timedelta(hours=1)).isoformat()},
    )
    assert r.status_code == 200
    our = [it for it in r.json() if it["station_id"] == str(temp_station.id)]
    assert len(our) == 1
    item = our[0]
    assert item["count"] == 3
    assert item["min_sec"] == 10.0
    assert item["max_sec"] == 30.0
    assert item["avg_sec"] == 20.0
    assert item["median_sec"] == 20.0  # средний из [10, 20, 30]


async def test_cycle_times_unpaired_start_ignored(
    supervisor_client: AsyncClient, temp_station: Station,
) -> None:
    """start без stop не учитывается — нечего считать."""
    now = datetime.now(timezone.utc)
    await _add(temp_station.id, EventType.start, now - timedelta(minutes=5))
    # Никакого stop

    r = await supervisor_client.get(
        "/api/v1/analytics/cycle_times",
        params={"since": (now - timedelta(hours=1)).isoformat()},
    )
    assert r.status_code == 200
    our = [it for it in r.json() if it["station_id"] == str(temp_station.id)]
    assert our == []  # без пары — нет записи
