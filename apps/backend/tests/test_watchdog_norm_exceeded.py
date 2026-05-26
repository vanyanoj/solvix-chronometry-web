"""Тесты детектора `norm_exceeded` (этап 2 watchdog)."""

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
from solvix_chronometry.models.processes import Process
from solvix_chronometry.watchdog.detectors.norm_exceeded import detect_norm_exceeded


@pytest_asyncio.fixture
async def temp_station() -> AsyncIterator[Station]:
    """Свежий станок для теста + cleanup всех связанных events/processes."""
    sid: UUID | None = None
    try:
        async with SessionLocal() as session:
            line = (await session.execute(select(Line).limit(1))).scalar_one_or_none()
            if line is None:
                raise RuntimeError("Нет Line в БД. Запусти scripts/seed_minimal.py.")
            unique = uuid4().hex[:8]
            st = Station(
                line_id=line.id,
                name=f"NormTest-{unique[:6]}",
                terminal_mac=f"02:{unique[0:2]}:{unique[2:4]}:{unique[4:6]}:77:77",
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
                    await session.execute(delete(Process).where(Process.station_hint == sid))
                    await session.execute(delete(Station).where(Station.id == sid))


async def _create_process(station_id: UUID, nominal_sec: int = 60, threshold_pct: int = 30) -> UUID:
    """Создать процесс для станка. Возвращает id."""
    async with SessionLocal() as session:
        proc = Process(
            input_type_1="A",
            input_type_2="B",
            output_type="C",
            station_hint=station_id,
            nominal_duration_sec=nominal_sec,
            anomaly_threshold_pct=threshold_pct,
            valid_from=datetime.now(timezone.utc) - timedelta(days=1),
        )
        session.add(proc)
        await session.commit()
        await session.refresh(proc)
        return proc.id


async def _create_event(station_id: UUID, event_type: EventType, ts: datetime) -> UUID:
    """Создать event на станке с заданным timestamp. Возвращает id."""
    async with SessionLocal() as session:
        ev = Event(
            timestamp=ts,
            received_at=ts,
            station_id=station_id,
            event_type=event_type,
        )
        session.add(ev)
        await session.commit()
        await session.refresh(ev)
        return ev.id


async def _count_norm_exceeded(station_id: UUID) -> UUID:
    async with SessionLocal() as session:
        anomalies = (await session.execute(
            select(Event)
            .where(Event.station_id == station_id)
            .where(Event.event_type == EventType.anomaly)
        )).scalars().all()
        return sum(1 for a in anomalies if a.details and a.details.get("kind") == "norm_exceeded")


# === Тесты ===

async def test_no_process_no_anomaly(temp_station: Station) -> None:
    """Нет процесса в БД для станка → детектор молчит."""
    now = datetime.now(timezone.utc)
    await _create_event(temp_station.id, EventType.start, now - timedelta(minutes=10))

    async with SessionLocal() as session:
        created = await detect_norm_exceeded(session)
        await session.commit()

    assert created == 0
    assert await _count_norm_exceeded(temp_station.id) == 0


async def test_short_operation_no_anomaly(temp_station: Station) -> None:
    """Операция короче порога → нет аномалии."""
    await _create_process(temp_station.id, nominal_sec=600, threshold_pct=30)
    now = datetime.now(timezone.utc)
    await _create_event(temp_station.id, EventType.start, now - timedelta(seconds=30))

    async with SessionLocal() as session:
        created = await detect_norm_exceeded(session)
        await session.commit()

    assert created == 0
    assert await _count_norm_exceeded(temp_station.id) == 0


async def test_long_operation_creates_anomaly(temp_station: Station) -> None:
    """Операция превысила норматив → anomaly создана с правильными деталями."""
    process_id = await _create_process(temp_station.id, nominal_sec=60, threshold_pct=30)
    now = datetime.now(timezone.utc)
    start_id = await _create_event(temp_station.id, EventType.start, now - timedelta(minutes=5))

    async with SessionLocal() as session:
        created = await detect_norm_exceeded(session)
        await session.commit()

    assert created == 1
    assert await _count_norm_exceeded(temp_station.id) == 1

    # Проверяем содержимое details
    async with SessionLocal() as session:
        anomaly = (await session.execute(
            select(Event)
            .where(Event.station_id == temp_station.id)
            .where(Event.event_type == EventType.anomaly)
            .limit(1)
        )).scalar_one()
        assert anomaly.details["kind"] == "norm_exceeded"
        assert anomaly.details["start_event_id"] == str(start_id)
        assert anomaly.details["nominal_sec"] == 60
        assert anomaly.details["threshold_sec"] == 78.0  # 60 * 1.30
        assert anomaly.details["process_id"] == str(process_id)
        assert anomaly.details["duration_actual_sec"] >= 295  # ~5 минут (даём допуск)


async def test_idempotency(temp_station: Station) -> None:
    """Повторный прогон не создаёт дубль anomaly для того же start_event."""
    await _create_process(temp_station.id, nominal_sec=60, threshold_pct=30)
    now = datetime.now(timezone.utc)
    await _create_event(temp_station.id, EventType.start, now - timedelta(minutes=5))

    async with SessionLocal() as session:
        n1 = await detect_norm_exceeded(session)
        await session.commit()
    async with SessionLocal() as session:
        n2 = await detect_norm_exceeded(session)
        await session.commit()

    assert n1 == 1
    assert n2 == 0
    assert await _count_norm_exceeded(temp_station.id) == 1


async def test_pause_subtracted(temp_station: Station) -> None:
    """Пауза 250с внутри 300с-операции → effective 50с < 78с порог → нет аномалии."""
    await _create_process(temp_station.id, nominal_sec=60, threshold_pct=30)
    now = datetime.now(timezone.utc)
    await _create_event(temp_station.id, EventType.start, now - timedelta(seconds=300))
    await _create_event(temp_station.id, EventType.break_start, now - timedelta(seconds=270))
    await _create_event(temp_station.id, EventType.break_end, now - timedelta(seconds=20))

    async with SessionLocal() as session:
        created = await detect_norm_exceeded(session)
        await session.commit()

    assert created == 0
    assert await _count_norm_exceeded(temp_station.id) == 0


async def test_stop_makes_station_idle(temp_station: Station) -> None:
    """Если был stop после start — станок не активен, нет аномалии."""
    await _create_process(temp_station.id, nominal_sec=60, threshold_pct=30)
    now = datetime.now(timezone.utc)
    await _create_event(temp_station.id, EventType.start, now - timedelta(minutes=10))
    await _create_event(temp_station.id, EventType.stop, now - timedelta(minutes=8))

    async with SessionLocal() as session:
        created = await detect_norm_exceeded(session)
        await session.commit()

    assert created == 0
    assert await _count_norm_exceeded(temp_station.id) == 0
