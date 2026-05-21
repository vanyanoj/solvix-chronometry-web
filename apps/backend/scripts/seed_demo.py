"""Засеять 3 дополнительные станции + 3 операторов + 3 открытых смены
поверх существующей иерархии (которую создал seed_minimal.py).
Идемпотентен — если станция с именем уже есть, пропускает.
"""
import asyncio

from sqlalchemy import select

from solvix_chronometry.db import SessionLocal
from solvix_chronometry.models.hierarchy import Line, Station
from solvix_chronometry.models.people import NfcBadge, Shift, User
from solvix_chronometry.uuid_v7 import uuid7


EXTRA_STATIONS = [
    ("Test Station 2", "AA:BB:CC:DD:EE:02", "Алексей Иванов", "TEST-002"),
    ("Test Station 3", "AA:BB:CC:DD:EE:03", "Дмитрий Петров", "TEST-003"),
    ("Test Station 4", "AA:BB:CC:DD:EE:04", "Сергей Сидоров", "TEST-004"),
]


async def main():
    async with SessionLocal() as s:
        line = (await s.execute(select(Line).limit(1))).scalar_one_or_none()
        if line is None:
            print("ERROR: нет ни одной линии. Сначала запусти seed_minimal.py")
            return
        print(f"Using line {line.id}")

        for name, mac, operator_name, pass_code in EXTRA_STATIONS:
            existing = (await s.execute(
                select(Station).where(Station.name == name)
            )).scalar_one_or_none()
            if existing is not None:
                print(f"  {name}: already exists, skipping")
                continue

            station = Station(id=uuid7(), line_id=line.id, name=name, terminal_mac=mac)
            s.add(station)
            await s.flush()

            user = User(id=uuid7(), pass_code=pass_code, full_name=operator_name, active=True)
            badge = NfcBadge(id=uuid7(), uid=f"04:{mac}", status="free")
            s.add_all([user, badge])
            await s.flush()

            shift = Shift(id=uuid7(), user_id=user.id, badge_id=badge.id, station_id=station.id)
            s.add(shift)
            await s.commit()

            print(f"  {name}: created, operator={operator_name}, shift open")


if __name__ == "__main__":
    asyncio.run(main())
