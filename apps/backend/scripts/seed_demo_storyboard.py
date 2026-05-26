"""Мастер-seed для storyboard-демки.

Идемпотентный. Создаёт всё что нужно для режиссёрского сценария:
- 4 именованных оператора с pass_code OP-S1..OP-S4 (Петров / Иванов / Сидоров / Кузнецов)
- 4 NFC-бейджа BADGE-S1..BADGE-S4
- 4 активные смены (по одной на каждый из 4 станков) — операторы появляются в карточках
- 1 batch DEMO-STORY + 2 parts (D-S1-A, D-S2-A) для сценария
- Процессы на каждый станок (nominal=10c, threshold=10% → norm_exceeded за 11c)
- 4 break_reasons (smoke=30c — для pause_exceeded в сценарии)

Перед созданием активных смен закрывает все существующие — чтобы не было конфликтов.
"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from solvix_chronometry.db import SessionLocal
from solvix_chronometry.models.break_reasons import BreakReason
from solvix_chronometry.models.enums import (
    NfcBadgeStatus, PartStatus, ShiftClosedBy, UserRole,
)
from solvix_chronometry.models.hierarchy import Station
from solvix_chronometry.models.parts import Batch, Part
from solvix_chronometry.models.people import NfcBadge, Shift, User
from solvix_chronometry.models.processes import Process


OPERATORS = [
    ("OP-S1", "Петров А.С."),
    ("OP-S2", "Иванов А.А."),
    ("OP-S3", "Сидоров К.Л."),
    ("OP-S4", "Кузнецов И.В."),
]

BADGES = [f"BADGE-S{i}" for i in range(1, 5)]

BREAK_REASONS = [
    ("lunch", "Обед", 120),
    ("smoke", "Перекур", 30),
    ("toilet", "Туалет", 30),
    ("other", "Другое", 60),
]


async def get_or_create_user(session, pass_code, full_name):
    user = (await session.execute(
        select(User).where(User.pass_code == pass_code)
    )).scalar_one_or_none()
    if user is not None:
        # Обновим имя если оно сменилось (для повторного запуска)
        if user.full_name != full_name:
            user.full_name = full_name
        return user, False
    user = User(
        pass_code=pass_code,
        full_name=full_name,
        role=UserRole.operator,
        active=True,
    )
    session.add(user)
    await session.flush()
    return user, True


async def get_or_create_badge(session, uid):
    badge = (await session.execute(
        select(NfcBadge).where(NfcBadge.uid == uid)
    )).scalar_one_or_none()
    if badge is not None:
        return badge, False
    badge = NfcBadge(uid=uid, status=NfcBadgeStatus.bound)
    session.add(badge)
    await session.flush()
    return badge, True


async def close_existing_shifts(session):
    """Закрываем все активные смены — чтобы наш сид создал чистые новые."""
    active = (await session.execute(
        select(Shift).where(Shift.unbound_at.is_(None))
    )).scalars().all()
    for s in active:
        s.unbound_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        s.closed_by = ShiftClosedBy.supervisor
    return len(active)


async def create_shift(session, user, badge, station):
    shift = Shift(
        user_id=user.id,
        badge_id=badge.id,
        station_id=station.id,
        bound_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    session.add(shift)
    return shift


async def seed_processes(session, stations):
    created = 0
    for station in stations:
        existing = (await session.execute(
            select(Process).where(Process.station_hint == station.id)
        )).scalar_one_or_none()
        if existing is not None:
            continue
        proc = Process(
            input_type_1="A",
            input_type_2="B",
            output_type="C",
            station_hint=station.id,
            nominal_duration_sec=10,
            anomaly_threshold_pct=10,
            valid_from=datetime.now(timezone.utc) - timedelta(days=1),
        )
        session.add(proc)
        created += 1
    return created


async def seed_break_reasons(session):
    created = 0
    for code, name, max_sec in BREAK_REASONS:
        existing = (await session.execute(
            select(BreakReason).where(BreakReason.code == code)
        )).scalar_one_or_none()
        if existing is not None:
            continue
        session.add(BreakReason(code=code, name=name, max_duration_sec=max_sec))
        created += 1
    return created


async def seed_storyboard_parts(session):
    """Parts D-S1-A и D-S2-A в batch DEMO-STORY."""
    existing_batch = (await session.execute(
        select(Batch).where(Batch.part_type == "STORY")
    )).scalar_one_or_none()
    if existing_batch is not None:
        return 0

    batch = Batch(part_type="STORY")
    session.add(batch)
    await session.flush()

    for pid in ["D-S1-A", "D-S2-A"]:
        part = Part(
            id=pid,
            base_id=pid.rsplit("-", 1)[0],
            version=0,
            type="A",
            status=PartStatus.active,
            parents=[],
            batch_id=batch.id,
        )
        session.add(part)
    return 2


async def main():
    async with SessionLocal() as session:
        print("=" * 60)
        print("Seed storyboard demo")
        print("=" * 60)

        stations = list((await session.execute(
            select(Station).order_by(Station.name)
        )).scalars().all())

        if len(stations) < 4:
            print(f"ERROR: нужно 4 станции, найдено {len(stations)}.")
            print("Запусти seed_minimal.py + seed_demo.py")
            return

        # 1. Закрыть существующие активные смены
        n_closed = await close_existing_shifts(session)
        print(f"\n1. Closed {n_closed} existing active shifts")

        # 2. Операторы, бейджи, смены — по одному на каждый из 4 станков
        print("\n2. Operators / Badges / Shifts:")
        for i, station in enumerate(stations[:4]):
            pass_code, full_name = OPERATORS[i]
            badge_uid = BADGES[i]

            user, user_new = await get_or_create_user(session, pass_code, full_name)
            badge, badge_new = await get_or_create_badge(session, badge_uid)
            shift = await create_shift(session, user, badge, station)

            print(f"  • {station.name}: {full_name} ({pass_code}) + {badge_uid}"
                  f" {'[new]' if user_new else '[existing]'}")

        # 3. Процессы
        print("\n3. Processes:")
        n_proc = await seed_processes(session, stations)
        print(f"  Created {n_proc} processes (nominal=10s, threshold=10%)")

        # 4. Break reasons
        print("\n4. Break reasons:")
        n_br = await seed_break_reasons(session)
        print(f"  Created {n_br} break_reasons")

        # 5. Storyboard parts
        print("\n5. Storyboard parts:")
        n_pa = await seed_storyboard_parts(session)
        print(f"  Created {n_pa} parts (D-S1-A, D-S2-A)")

        await session.commit()

        print("\n" + "=" * 60)
        print("✓ Storyboard demo ready")
        print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
