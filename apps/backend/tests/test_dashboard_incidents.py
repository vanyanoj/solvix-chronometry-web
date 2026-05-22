"""Тесты GET /dashboard/incidents (supervisor-блок).

Покрытие: auth (401/403), 200 базовый, фильтр по since, валидация,
проверка что созданный anomaly-event попадает в ответ.
"""

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
from solvix_chronometry.uuid_v7 import uuid7


# === Fixtures ===

@pytest_asyncio.fixture
async def test_station_for_incident() -> AsyncIterator[Station]:
    """Временный станок для теста incident-эндпоинта."""
    sid: UUID | None = None
    try:
        async with SessionLocal() as session:
            line = (await session.execute(select(Line).limit(1))).scalar_one_or_none()
            if line is None:
                raise RuntimeError("Нет Line в БД. Запусти scripts/seed_minimal.py.")
            unique = uuid4().hex[:8]
            station = Station(
                line_id=line.id,
                name=f"IncidentStation-{unique[:6]}",
                terminal_mac=f"02:{unique[0:2]}:{unique[2:4]}:{unique[4:6]}:01:01",
            )
            session.add(station)
            await session.commit()
            await session.refresh(station)
            sid = station.id
        async with SessionLocal() as session:
            station = (await session.execute(select(Station).where(Station.id == sid))).scalar_one()
        yield station
    finally:
        if sid:
            async with SessionLocal() as session:
                async with session.begin():
                    await session.execute(delete(Event).where(Event.station_id == sid))
                    await session.execute(delete(Station).where(Station.id == sid))


@pytest_asyncio.fixture
async def anomaly_event(test_station_for_incident: Station) -> AsyncIterator[Event]:
    """Свежий event типа anomaly на нашем тестовом станке."""
    event_id: UUID | None = None
    try:
        async with SessionLocal() as session:
            now = datetime.now(timezone.utc)
            event = Event(
                timestamp=now,
                received_at=now,
                station_id=test_station_for_incident.id,
                event_type=EventType.anomaly,
                details={"kind": "norm_exceeded", "duration_actual_sec": 380},
            )
            session.add(event)
            await session.commit()
            await session.refresh(event)
            event_id = event.id
            ev_obj = event
        yield ev_obj
    finally:
        if event_id:
            async with SessionLocal() as session:
                async with session.begin():
                    await session.execute(delete(Event).where(Event.id == event_id))


# === Auth ===

async def test_no_token_returns_401(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/dashboard/incidents")).status_code == 401


async def test_warehouse_role_forbidden(warehouse_client: AsyncClient) -> None:
    assert (await warehouse_client.get("/api/v1/dashboard/incidents")).status_code == 403


# === Base ===

async def test_basic_returns_200(supervisor_client: AsyncClient) -> None:
    r = await supervisor_client.get("/api/v1/dashboard/incidents")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_pagination_validation(supervisor_client: AsyncClient) -> None:
    assert (await supervisor_client.get("/api/v1/dashboard/incidents?limit=0")).status_code == 422
    assert (await supervisor_client.get("/api/v1/dashboard/incidents?limit=500")).status_code == 422
    assert (await supervisor_client.get("/api/v1/dashboard/incidents?offset=-1")).status_code == 422


async def test_anomaly_event_appears_in_response(
    supervisor_client: AsyncClient,
    anomaly_event: Event,
    test_station_for_incident: Station,
) -> None:
    """Созданный anomaly-event попадает в ленту инцидентов с правильными полями."""
    r = await supervisor_client.get("/api/v1/dashboard/incidents?limit=200")
    assert r.status_code == 200
    items = r.json()

    our = next((it for it in items if it["id"] == str(anomaly_event.id)), None)
    assert our is not None, f"Event {anomaly_event.id} не найден в ленте"

    assert our["event_type"] == "anomaly"
    assert our["station_id"] == str(test_station_for_incident.id)
    assert our["station_name"] == test_station_for_incident.name
    assert our["details"] == {"kind": "norm_exceeded", "duration_actual_sec": 380}


async def test_since_filter_excludes_old(
    supervisor_client: AsyncClient,
    anomaly_event: Event,
) -> None:
    """Если since в будущем — лента пустая (наше событие в прошлом)."""
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    r = await supervisor_client.get("/api/v1/dashboard/incidents", params={"since": future})
    assert r.status_code == 200
    ids = [it["id"] for it in r.json()]
    assert str(anomaly_event.id) not in ids


async def test_since_filter_includes_recent(
    supervisor_client: AsyncClient,
    anomaly_event: Event,
) -> None:
    """Если since час назад — наше event (создано только что) попадает."""
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    r = await supervisor_client.get("/api/v1/dashboard/incidents", params={"since": one_hour_ago, "limit": 200})
    assert r.status_code == 200
    ids = [it["id"] for it in r.json()]
    assert str(anomaly_event.id) in ids
