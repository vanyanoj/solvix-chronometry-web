"""Засевает процессы, break_reasons и demo-parts для демки аномалий.

Идемпотентный — можно запускать многократно, не плодит дубли.

Создаёт:
- 1 процесс на каждый станок (nominal=10c, threshold=10% → срабатывает за ~11c)
- 4 break_reason (lunch/smoke/toilet/other) с короткими порогами (30c-120c)
- 4 parts для symulator аномалий (по одному на станок, через 1 batch)
"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from solvix_chronometry.db import SessionLocal
from solvix_chronometry.models.break_reasons import BreakReason
from solvix_chronometry.models.enums import PartStatus
from solvix_chronometry.models.hierarchy import Station
from solvix_chronometry.models.parts import Batch, Part
from solvix_chronometry.models.processes import Process


BREAK_REASONS = [
    ("lunch", "Обед", 120),
    ("smoke", "Перекур", 30),
    ("toilet", "Туалет", 30),
    ("other", "Другое", 60),
]


async def seed_processes(session) -> int:
    """Создаём по одному процессу на каждый станок."""
    stations = (await session.execute(select(Station))).scalars().all()
    if not stations:
        print("ERROR: нет станций в БД. Запусти seed_minimal.py + seed_demo.py")
        return 0

    created = 0
    for station in stations:
        existing = (await session.execute(
            select(Process).where(Process.station_hint == station.id)
        )).scalar_one_or_none()
        if existing is not None:
            print(f"  ✓ Process for {station.name} already exists, skip")
            continue

        proc = Process(
            input_type_1="A",
            input_type_2="B",
            output_type="C",
            station_hint=station.id,
            nominal_duration_sec=10,   # 10 сек норма — быстрый триггер для демки
            anomaly_threshold_pct=10,  # +10% → срабатывает на 11 сек
            valid_from=datetime.now(timezone.utc) - timedelta(days=1),
        )
        session.add(proc)
        created += 1
        print(f"  + Process for {station.name} (nominal=10s, threshold=10%)")
    return created


async def seed_break_reasons(session) -> int:
    """Создаём 4 break_reasons если их нет."""
    created = 0
    for code, name, max_sec in BREAK_REASONS:
        existing = (await session.execute(
            select(BreakReason).where(BreakReason.code == code)
        )).scalar_one_or_none()
        if existing is not None:
            print(f"  ✓ Break reason '{code}' already exists, skip")
            continue
        session.add(BreakReason(code=code, name=name, max_duration_sec=max_sec))
        created += 1
        print(f"  + Break reason '{code}' (max={max_sec}s)")
    return created


async def seed_demo_parts(session) -> int:
    """Создаём 4 части (по одной на станок) для transit_stuck симуляции."""
    stations = (await session.execute(select(Station))).scalars().all()

    existing_batch = (await session.execute(
        select(Batch).where(Batch.part_type == "DEMO")
    )).scalar_one_or_none()

    if existing_batch is not None:
        print("  ✓ Demo batch already exists, skip")
        return 0

    batch = Batch(part_type="DEMO")
    session.add(batch)
    await session.flush()  # получить batch.id

    created = 0
    for i, st in enumerate(stations, start=1):
        part = Part(
            id=f"DEMO-{i:03d}.0",
            base_id=f"DEMO-{i:03d}",
            version=0,
            type="A",
            status=PartStatus.active,
            parents=[],
            batch_id=batch.id,
        )
        session.add(part)
        created += 1
        print(f"  + Part DEMO-{i:03d}.0 for {st.name}")
    return created


async def main() -> None:
    async with SessionLocal() as session:
        print("=" * 60)
        print("Seeding demo data")
        print("=" * 60)

        print("\n1. Processes:")
        n1 = await seed_processes(session)

        print("\n2. Break reasons:")
        n2 = await seed_break_reasons(session)

        print("\n3. Demo parts:")
        n3 = await seed_demo_parts(session)

        await session.commit()

        print("\n" + "=" * 60)
        print(f"Created: {n1} processes, {n2} break_reasons, {n3} parts")
        print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
