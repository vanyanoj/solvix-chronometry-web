"""Тесты детектора `pause_exceeded` (этап 3 watchdog)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest_asyncio
from sqlalchemy import delete, select

from solvix_chronometry.db import SessionLocal
from solvix_chronometry.models.break_reasons import BreakReason
from solvix_chronometry.models.enums import EventType
from solvix_chronometry.models.events import Event
from solvix_chronometry.models.hierarchy import Line, Station
from solvix_chronometry.core.detectors.pause_exceeded import detect_pause_exceeded


@pytest_asyncio.fixture
async def temp_station() -> AsyncIterator[Station]:
    """Свежий станок + cleanup events."""
    sid: UUID | None = None
    try:
        async with SessionLocal() as session:
            line = (await session.execute(select(Line).limit(1))).scalar_one_or_none()
            if line is None:
                raise RuntimeError("Нет Line в БД.")
            unique = uuid4().hex[:8]
            st = Station(
                line_id=line.id,
                name=f"PauseTest-{unique[:6]}",
                terminal_mac=f"02:{unique[0:2]}:{unique[2:4]}:{unique[4:6]}:88:88",
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


@pytest_asyncio.fixture
async def temp_break_reason() -> AsyncIterator[BreakReason]:
    """Тестовая причина с порогом 60 секунд."""
    rid: UUID | None = None
    try:
        async with SessionLocal() as session:
            unique = uuid4().hex[:6]
            br = BreakReason(
                code=f"test-{unique}",
                name=f"Test reason {unique}",
                max_duration_sec=60,
            )
            session.add(br)
            await session.commit()
            await session.refresh(br)
            rid = br.id
        async with SessionLocal() as session:
            yield (await session.execute(select(BreakReason).where(BreakReason.id == rid))).scalar_one()
    finally:
        if rid:
            async with SessionLocal() as session:
                async with session.begin():
                    await session.execute(delete(BreakReason).where(BreakReason.id == rid))


async def _create_break_event(
    station_id: UUID,
    event_type: EventType,
    ts: datetime,
    details: dict | None = None,
) -> UUID:
    async with SessionLocal() as session:
        ev = Event(
            timestamp=ts,
            received_at=ts,
            station_id=station_id,
            event_type=event_type,
            details=details,
        )
        session.add(ev)
        await session.commit()
        await session.refresh(ev)
        return ev.id


async def _count_pause_exceeded(station_id: UUID) -> int:
    async with SessionLocal() as session:
        anomalies = (await session.execute(
            select(Event)
            .where(Event.station_id == station_id)
            .where(Event.event_type == EventType.anomaly)
        )).scalars().all()
        return sum(1 for a in anomalies if a.details and a.details.get("kind") == "pause_exceeded")


# === Тесты ===

async def test_no_break_no_anomaly(temp_station: Station) -> None:
    """Нет ни одного break_start → детектор молчит."""
    async with SessionLocal() as session:
        created = await detect_pause_exceeded(session)
        await session.commit()
    assert created == 0


async def test_short_pause_no_anomaly(temp_station: Station, temp_break_reason: BreakReason) -> None:
    """Пауза короче порога → нет аномалии."""
    now = datetime.now(timezone.utc)
    await _create_break_event(
        temp_station.id, EventType.break_start, now - timedelta(seconds=30),
        details={"reason_id": str(temp_break_reason.id)},
    )

    async with SessionLocal() as session:
        created = await detect_pause_exceeded(session)
        await session.commit()

    assert created == 0
    assert await _count_pause_exceeded(temp_station.id) == 0


async def test_long_pause_creates_anomaly(temp_station: Station, temp_break_reason: BreakReason) -> None:
    """Пауза 5 минут с порогом 60 сек → создана аномалия с правильными деталями."""
    now = datetime.now(timezone.utc)
    bs_id = await _create_break_event(
        temp_station.id, EventType.break_start, now - timedelta(minutes=5),
        details={"reason_id": str(temp_break_reason.id), "reason_code": temp_break_reason.code},
    )

    async with SessionLocal() as session:
        created = await detect_pause_exceeded(session)
        await session.commit()

    assert created == 1
    assert await _count_pause_exceeded(temp_station.id) == 1

    async with SessionLocal() as session:
        anomaly = (await session.execute(
            select(Event)
            .where(Event.station_id == temp_station.id)
            .where(Event.event_type == EventType.anomaly)
            .limit(1)
        )).scalar_one()
        assert anomaly.details["kind"] == "pause_exceeded"
        assert anomaly.details["break_start_event_id"] == str(bs_id)
        assert anomaly.details["reason_id"] == str(temp_break_reason.id)
        assert anomaly.details["reason_code"] == temp_break_reason.code
        assert anomaly.details["max_duration_sec"] == 60
        assert anomaly.details["duration_actual_sec"] >= 295  # ~5 минут


async def test_closed_pause_no_anomaly(temp_station: Station, temp_break_reason: BreakReason) -> None:
    """break_start + break_end → пауза закрыта, нет аномалии."""
    now = datetime.now(timezone.utc)
    await _create_break_event(
        temp_station.id, EventType.break_start, now - timedelta(minutes=10),
        details={"reason_id": str(temp_break_reason.id)},
    )
    await _create_break_event(temp_station.id, EventType.break_end, now - timedelta(seconds=30))

    async with SessionLocal() as session:
        created = await detect_pause_exceeded(session)
        await session.commit()

    assert created == 0
    assert await _count_pause_exceeded(temp_station.id) == 0


async def test_idempotency(temp_station: Station, temp_break_reason: BreakReason) -> None:
    """Повторный прогон не создаёт дубль для того же break_start."""
    now = datetime.now(timezone.utc)
    await _create_break_event(
        temp_station.id, EventType.break_start, now - timedelta(minutes=5),
        details={"reason_id": str(temp_break_reason.id)},
    )

    async with SessionLocal() as session:
        n1 = await detect_pause_exceeded(session)
        await session.commit()
    async with SessionLocal() as session:
        n2 = await detect_pause_exceeded(session)
        await session.commit()

    assert n1 == 1
    assert n2 == 0
    assert await _count_pause_exceeded(temp_station.id) == 1


async def test_missing_reason_id_no_anomaly(temp_station: Station) -> None:
    """break_start без reason_id в details → молчим."""
    now = datetime.now(timezone.utc)
    await _create_break_event(
        temp_station.id, EventType.break_start, now - timedelta(minutes=5),
        details={"something_else": "value"},
    )

    async with SessionLocal() as session:
        created = await detect_pause_exceeded(session)
        await session.commit()

    assert created == 0
    assert await _count_pause_exceeded(temp_station.id) == 0


async def test_old_break_ignored(temp_station: Station, temp_break_reason: BreakReason) -> None:
    """break_start старше 8 часов игнорируется (это уже не пауза, а конец смены)."""
    now = datetime.now(timezone.utc)
    await _create_break_event(
        temp_station.id, EventType.break_start, now - timedelta(hours=10),
        details={"reason_id": str(temp_break_reason.id)},
    )

    async with SessionLocal() as session:
        created = await detect_pause_exceeded(session)
        await session.commit()

    assert created == 0
    assert await _count_pause_exceeded(temp_station.id) == 0
