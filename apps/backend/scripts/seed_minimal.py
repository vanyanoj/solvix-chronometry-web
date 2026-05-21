"""One-off seed: minimal hierarchy so MQTT events have a valid station_id FK.
Run from apps/backend with venv activated: python scripts/seed_minimal.py
"""
import asyncio

from solvix_chronometry.db import SessionLocal
from solvix_chronometry.models.hierarchy import Site, Workshop, Line, Station
from solvix_chronometry.uuid_v7 import uuid7


async def main():
    async with SessionLocal() as session:
        site = Site(id=uuid7(), name="Test Site")
        workshop = Workshop(id=uuid7(), site_id=site.id, name="Test Workshop")
        line = Line(id=uuid7(), workshop_id=workshop.id, name="Test Line")
        station = Station(
            id=uuid7(),
            line_id=line.id,
            name="Test Station 1",
            terminal_mac="AA:BB:CC:DD:EE:01",
        )
        session.add_all([site, workshop, line, station])
        await session.commit()

        print()
        print("Seeded minimal hierarchy:")
        print(f"  station_id = {station.id}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
