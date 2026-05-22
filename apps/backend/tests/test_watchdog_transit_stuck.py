"""Тесты детектора `transit_stuck` (этап 5 watchdog)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest_asyncio
from sqlalchemy import delete, select

from solvix_chronometry.db import SessionLocal
from solvix_chronometry.models.parts import Batch
from solvix_chronometry.models.enums import EventType, PartStatus
from solvix_chronometry.models.events import Event
from solvix_chronometry.models.hierarchy import Line, Station
from solvix_chronometry.models.parts import Part
from solvix_chronometry.watchdog.detectors.transit_stuck import detect_transit_stuck


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
                name=f"TransitTest-{unique[:6]}",
                terminal_mac=f"02:{unique[0:2]}:{unique[2:4]}:{unique[4:6]}:44:44",
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
async def temp_part() -> AsyncIterator[str]:
    """Создать временные batch + part. Вернуть part.id."""
    batch_id = None
    part_id_str: str | None = None
    try:
        async with SessionLocal() as session:
            batch = Batch(part_type="A")
            session.add(batch)
            await session.commit()
            await session.refresh(batch)
            batch_id = batch.id

            unique = uuid4().hex[:6]
            part = Part(
                id=f"TRT-{unique}.0",
                base_id=f"TRT-{unique}",
                version=0,
                type="A",
                status=PartStatus.active,
                parents=[],
                batch_id=batch.id,
            )
            session.add(part)
            await session.commit()
            await session.refresh(part)
            part_id_str = part.id
        yield part_id_str
    finally:
        async with SessionLocal() as session:
            async with session.begin():
                if part_id_str:
                    await session.execute(delete(Event).where(Event.part_id == part_id_str))
                    await session.execute(delete(Part).where(Part.id == part_id_str))
                if batch_id:
                    await session.execute(delete(Batch).where(Batch.id == batch_id))


async def _create_event(
    station_id: UUID,
    event_type: EventType,
    ts: datetime,
    part_id: str | None = None,
) -> UUID:
    async with SessionLocal() as session:
        ev = Event(
            timestamp=ts, received_at=ts,
            station_id=station_id, event_type=event_type, part_id=part_id,
        )
        session.add(ev)
        await session.commit()
        await session.refresh(ev)
        return ev.id


async def _count_transit_stuck(part_id: str) -> int:
    async with SessionLocal() as session:
        anomalies = (await session.execute(
            select(Event)
            .where(Event.event_type == EventType.anomaly)
            .where(Event.part_id == part_id)
        )).scalars().all()
        return sum(1 for a in anomalies if a.details and a.details.get("kind") == "transit_stuck")


# === Тесты ===

async def test_no_scan_out_no_anomaly(temp_station: Station) -> None:
    """Нет scan_out → детектор молчит."""
    async with SessionLocal() as session:
        created = await detect_transit_stuck(session)
        await session.commit()
    assert created == 0


async def test_recent_scan_out_no_anomaly(temp_station: Station, temp_part: str) -> None:
    """scan_out минуту назад → не флагнуто (порог 5 мин)."""
    now = datetime.now(timezone.utc)
    await _create_event(temp_station.id, EventType.scan_out, now - timedelta(minutes=1), part_id=temp_part)

    async with SessionLocal() as session:
        created = await detect_transit_stuck(session)
        await session.commit()

    assert created == 0
    assert await _count_transit_stuck(temp_part) == 0


async def test_long_transit_creates_anomaly(temp_station: Station, temp_part: str) -> None:
    """scan_out 30 мин назад, нет scan_in → anomaly."""
    now = datetime.now(timezone.utc)
    so_id = await _create_event(temp_station.id, EventType.scan_out, now - timedelta(minutes=30), part_id=temp_part)

    async with SessionLocal() as session:
        created = await detect_transit_stuck(session)
        await session.commit()

    assert created == 1
    assert await _count_transit_stuck(temp_part) == 1

    async with SessionLocal() as session:
        anomaly = (await session.execute(
            select(Event)
            .where(Event.event_type == EventType.anomaly)
            .where(Event.part_id == temp_part)
            .limit(1)
        )).scalar_one()
        assert anomaly.details["kind"] == "transit_stuck"
        assert anomaly.details["scan_out_event_id"] == str(so_id)
        assert anomaly.details["scan_out_station_id"] == str(temp_station.id)
        assert anomaly.details["threshold_sec"] == TRANSIT_STUCK_THRESHOLD_SEC_EXPECTED
        assert anomaly.details["duration_actual_sec"] >= 1795


async def test_completed_transit_no_anomaly(temp_station: Station, temp_part: str) -> None:
    """scan_out + scan_in (где угодно) с тем же part_id → транзит завершён."""
    now = datetime.now(timezone.utc)
    await _create_event(temp_station.id, EventType.scan_out, now - timedelta(minutes=30), part_id=temp_part)
    await _create_event(temp_station.id, EventType.scan_in, now - timedelta(minutes=25), part_id=temp_part)

    async with SessionLocal() as session:
        created = await detect_transit_stuck(session)
        await session.commit()

    assert created == 0
    assert await _count_transit_stuck(temp_part) == 0


async def test_idempotency(temp_station: Station, temp_part: str) -> None:
    """Повторный прогон не создаёт дубль."""
    now = datetime.now(timezone.utc)
    await _create_event(temp_station.id, EventType.scan_out, now - timedelta(minutes=30), part_id=temp_part)

    async with SessionLocal() as session:
        n1 = await detect_transit_stuck(session)
        await session.commit()
    async with SessionLocal() as session:
        n2 = await detect_transit_stuck(session)
        await session.commit()

    assert n1 == 1
    assert n2 == 0
    assert await _count_transit_stuck(temp_part) == 1


async def test_old_scan_out_ignored(temp_station: Station, temp_part: str) -> None:
    """scan_out старше 2 часов игнорируется (за окном)."""
    now = datetime.now(timezone.utc)
    await _create_event(temp_station.id, EventType.scan_out, now - timedelta(hours=3), part_id=temp_part)

    async with SessionLocal() as session:
        created = await detect_transit_stuck(session)
        await session.commit()

    assert created == 0
    assert await _count_transit_stuck(temp_part) == 0


# Импорт константы из детектора чтобы не дублировать
from solvix_chronometry.watchdog.detectors.transit_stuck import TRANSIT_STUCK_THRESHOLD_SEC as TRANSIT_STUCK_THRESHOLD_SEC_EXPECTED  # noqa: E402
