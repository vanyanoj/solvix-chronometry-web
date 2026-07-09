"""Тесты детектора `station_idle` (этап 4 watchdog)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest_asyncio
from sqlalchemy import delete, select

from solvix_chronometry.db import SessionLocal
from solvix_chronometry.models.enums import EventType
from solvix_chronometry.models.events import Event
from solvix_chronometry.models.hierarchy import Line, Station
from solvix_chronometry.models.people import NfcBadge, Shift, User
from solvix_chronometry.core.detectors.station_idle import detect_station_idle


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
                name=f"IdleTest-{unique[:6]}",
                terminal_mac=f"02:{unique[0:2]}:{unique[2:4]}:{unique[4:6]}:55:55",
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
                    await session.execute(delete(Shift).where(Shift.station_id == sid))
                    await session.execute(delete(Station).where(Station.id == sid))


@pytest_asyncio.fixture
async def active_shift(temp_station: Station, operator_user: User) -> AsyncIterator[Shift]:
    """Активная смена на temp_station, bound_at=now-1ч."""
    shift_id: UUID | None = None
    badge_id: UUID | None = None
    try:
        async with SessionLocal() as session:
            badge = NfcBadge(uid=f"IDLE-{uuid4().hex[:8]}")
            session.add(badge)
            await session.commit()
            await session.refresh(badge)
            badge_id = badge.id

            shift = Shift(
                user_id=operator_user.id,
                badge_id=badge.id,
                station_id=temp_station.id,
                bound_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
            session.add(shift)
            await session.commit()
            await session.refresh(shift)
            shift_id = shift.id
        async with SessionLocal() as session:
            yield (await session.execute(select(Shift).where(Shift.id == shift_id))).scalar_one()
    finally:
        async with SessionLocal() as session:
            async with session.begin():
                if shift_id:
                    await session.execute(delete(Event).where(Event.shift_id == shift_id))
                    await session.execute(delete(Shift).where(Shift.id == shift_id))
                if badge_id:
                    await session.execute(delete(NfcBadge).where(NfcBadge.id == badge_id))


async def _create_event(station_id: UUID, event_type: EventType, ts: datetime) -> UUID:
    async with SessionLocal() as session:
        ev = Event(
            timestamp=ts, received_at=ts,
            station_id=station_id, event_type=event_type,
        )
        session.add(ev)
        await session.commit()
        await session.refresh(ev)
        return ev.id


async def _count_station_idle(station_id: UUID) -> int:
    async with SessionLocal() as session:
        anomalies = (await session.execute(
            select(Event)
            .where(Event.station_id == station_id)
            .where(Event.event_type == EventType.anomaly)
        )).scalars().all()
        return sum(1 for a in anomalies if a.details and a.details.get("kind") == "station_idle")


# === Тесты ===

async def test_no_active_shifts_no_anomaly(temp_station: Station) -> None:
    """Активных смен нет → детектор молчит."""
    async with SessionLocal() as session:
        created = await detect_station_idle(session)
        await session.commit()
    assert created == 0


async def test_recent_event_no_anomaly(temp_station: Station, active_shift: Shift) -> None:
    """Событие минуту назад → не idle."""
    now = datetime.now(timezone.utc)
    await _create_event(temp_station.id, EventType.stop, now - timedelta(minutes=1))

    async with SessionLocal() as session:
        created = await detect_station_idle(session)
        await session.commit()

    assert created == 0
    assert await _count_station_idle(temp_station.id) == 0


async def test_long_idle_creates_anomaly(temp_station: Station, active_shift: Shift) -> None:
    """Последнее событие 30 мин назад → anomaly."""
    now = datetime.now(timezone.utc)
    last_id = await _create_event(temp_station.id, EventType.stop, now - timedelta(minutes=30))

    async with SessionLocal() as session:
        created = await detect_station_idle(session)
        await session.commit()

    assert created == 1
    assert await _count_station_idle(temp_station.id) == 1

    async with SessionLocal() as session:
        anomaly = (await session.execute(
            select(Event)
            .where(Event.station_id == temp_station.id)
            .where(Event.event_type == EventType.anomaly)
            .limit(1)
        )).scalar_one()
        assert anomaly.details["kind"] == "station_idle"
        assert anomaly.details["last_event_id"] == str(last_id)
        assert anomaly.details["threshold_sec"] == 15 * 60
        assert anomaly.details["duration_actual_sec"] >= 1795  # ~30 мин


async def test_active_operation_no_anomaly(temp_station: Station, active_shift: Shift) -> None:
    """Открытый `start` без stop → активная работа, не idle."""
    now = datetime.now(timezone.utc)
    await _create_event(temp_station.id, EventType.start, now - timedelta(minutes=30))

    async with SessionLocal() as session:
        created = await detect_station_idle(session)
        await session.commit()

    assert created == 0
    assert await _count_station_idle(temp_station.id) == 0


async def test_active_pause_no_anomaly(temp_station: Station, active_shift: Shift) -> None:
    """Открытый `break_start` без break_end → активная пауза, не idle."""
    now = datetime.now(timezone.utc)
    await _create_event(temp_station.id, EventType.break_start, now - timedelta(minutes=30))

    async with SessionLocal() as session:
        created = await detect_station_idle(session)
        await session.commit()

    assert created == 0
    assert await _count_station_idle(temp_station.id) == 0


async def test_no_events_after_bound(temp_station: Station, active_shift: Shift) -> None:
    """bound_at был 1ч назад, событий нет → idle с idle_since=bound_at."""
    async with SessionLocal() as session:
        created = await detect_station_idle(session)
        await session.commit()

    assert created == 1
    async with SessionLocal() as session:
        anomaly = (await session.execute(
            select(Event)
            .where(Event.station_id == temp_station.id)
            .where(Event.event_type == EventType.anomaly)
            .limit(1)
        )).scalar_one()
        assert anomaly.details["last_event_id"] is None
        assert anomaly.details["duration_actual_sec"] >= 3595  # ~1ч


async def test_idempotency(temp_station: Station, active_shift: Shift) -> None:
    """Повторный прогон не создаёт дубль."""
    now = datetime.now(timezone.utc)
    await _create_event(temp_station.id, EventType.stop, now - timedelta(minutes=30))

    async with SessionLocal() as session:
        n1 = await detect_station_idle(session)
        await session.commit()
    async with SessionLocal() as session:
        n2 = await detect_station_idle(session)
        await session.commit()

    assert n1 == 1
    assert n2 == 0
    assert await _count_station_idle(temp_station.id) == 1
