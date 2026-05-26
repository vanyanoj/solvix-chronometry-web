"""Тесты Этапа 1 watchdog — скелет и helper."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest_asyncio
from sqlalchemy import delete, select

from solvix_chronometry.db import SessionLocal
from solvix_chronometry.models.enums import EventType
from solvix_chronometry.models.events import Event
from solvix_chronometry.models.hierarchy import Line, Station
from solvix_chronometry.watchdog.helpers import create_anomaly_event
from solvix_chronometry.watchdog.runner import run_watchdog


@pytest_asyncio.fixture
async def temp_station() -> AsyncIterator[Station]:
    """Временный станок для тестов watchdog."""
    sid: UUID | None = None
    try:
        async with SessionLocal() as session:
            line = (await session.execute(select(Line).limit(1))).scalar_one_or_none()
            if line is None:
                raise RuntimeError("Нет Line в БД. Запусти scripts/seed_minimal.py.")
            unique = uuid4().hex[:8]
            st = Station(
                line_id=line.id,
                name=f"WatchdogTest-{unique[:6]}",
                terminal_mac=f"02:{unique[0:2]}:{unique[2:4]}:{unique[4:6]}:99:99",
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


# === Helper ===

async def test_helper_creates_anomaly_with_kind(temp_station: Station) -> None:
    """create_anomaly_event создаёт event типа anomaly с правильным details.kind."""
    async with SessionLocal() as session:
        ev = await create_anomaly_event(
            session,
            station_id=temp_station.id,
            kind="norm_exceeded",
            details={"duration_sec": 420, "nominal_sec": 300},
        )
        await session.commit()
        await session.refresh(ev)
        ev_id = ev.id
    try:
        async with SessionLocal() as session:
            stored = (await session.execute(select(Event).where(Event.id == ev_id))).scalar_one()
            assert stored.event_type == EventType.anomaly
            assert stored.station_id == temp_station.id
            assert stored.details == {
                "kind": "norm_exceeded",
                "duration_sec": 420,
                "nominal_sec": 300,
            }
            assert stored.shift_id is None
            assert stored.part_id is None
    finally:
        async with SessionLocal() as cleanup:
            async with cleanup.begin():
                await cleanup.execute(delete(Event).where(Event.id == ev_id))


async def test_helper_minimal_call_only_kind(temp_station: Station) -> None:
    """Минимальный вызов: только station_id + kind. Остальные поля nullable / дефолтные."""
    async with SessionLocal() as session:
        ev = await create_anomaly_event(
            session,
            station_id=temp_station.id,
            kind="station_idle",
        )
        await session.commit()
        await session.refresh(ev)
        ev_id = ev.id
    try:
        async with SessionLocal() as session:
            stored = (await session.execute(select(Event).where(Event.id == ev_id))).scalar_one()
            assert stored.details == {"kind": "station_idle"}
            assert stored.shift_id is None
            assert stored.part_id is None
            assert stored.timestamp is not None
    finally:
        async with SessionLocal() as cleanup:
            async with cleanup.begin():
                await cleanup.execute(delete(Event).where(Event.id == ev_id))


async def test_helper_custom_timestamp(temp_station: Station) -> None:
    """Если передан timestamp — он используется (а не now)."""
    custom_ts = datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    async with SessionLocal() as session:
        ev = await create_anomaly_event(
            session,
            station_id=temp_station.id,
            kind="pause_exceeded",
            timestamp=custom_ts,
        )
        await session.commit()
        await session.refresh(ev)
        ev_id = ev.id
    try:
        async with SessionLocal() as session:
            stored = (await session.execute(select(Event).where(Event.id == ev_id))).scalar_one()
            # Сравниваем приближённо (PG roundtrip может потерять микросекунды).
            assert abs((stored.timestamp - custom_ts).total_seconds()) < 1
    finally:
        async with SessionLocal() as cleanup:
            async with cleanup.begin():
                await cleanup.execute(delete(Event).where(Event.id == ev_id))


# === Runner ===

async def test_runner_starts_and_cancels_cleanly() -> None:
    """Runner стартует, не падает, корректно гасится по cancel()."""
    task = asyncio.create_task(run_watchdog())
    # Дать время на лог запуска и заход в первый sleep.
    await asyncio.sleep(0.1)
    assert not task.done(), "Watchdog должен жить — но упал сразу"

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert task.done()
