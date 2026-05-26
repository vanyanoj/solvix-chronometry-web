"""Стресс-тест: спам N событий через MQTT на максимальной скорости.

Запуск:
    python scripts/stress_test.py            # 1000 событий (по умолчанию)
    python scripts/stress_test.py 5000       # 5000 событий
    python scripts/stress_test.py 50000      # 50k — может быть больно

Измеряет: publish rate, drain time, end-to-end throughput.
"""
import asyncio
import json
import sys
import time
from datetime import datetime, timezone

import aiomqtt
from sqlalchemy import func, select

from solvix_chronometry.config import settings
from solvix_chronometry.db import SessionLocal
from solvix_chronometry.models.events import Event
from solvix_chronometry.models.hierarchy import Station
from solvix_chronometry.uuid_v7 import uuid7


EVENT_TYPES = ["scan_in", "start", "stop", "scan_out"]


async def get_stations() -> list[Station]:
    async with SessionLocal() as s:
        return list((await s.execute(select(Station))).scalars().all())


async def count_events() -> int:
    async with SessionLocal() as s:
        return (await s.execute(select(func.count()).select_from(Event))).scalar_one()


async def main(count: int) -> None:
    stations = await get_stations()
    if not stations:
        print("ERROR: нет станций в БД")
        sys.exit(1)

    print(f"Stations: {len(stations)}, target events: {count}\n")

    events_before = await count_events()
    print(f"Events in DB before: {events_before}\n")

    print(f"Connecting to MQTT at {settings.mqtt_host}:{settings.mqtt_port}...")
    async with aiomqtt.Client(settings.mqtt_host, port=settings.mqtt_port) as client:
        print("✓ Connected, publishing...\n")

        publish_start = time.monotonic()
        for i in range(count):
            station = stations[i % len(stations)]
            payload = {
                "id": str(uuid7()),
                "station_id": str(station.id),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": EVENT_TYPES[i % len(EVENT_TYPES)],
                "part_id": None,
                "details": None,
            }
            await client.publish(
                f"solvix/station/{station.id}/event",
                payload=json.dumps(payload),
                qos=1,
            )
            if (i + 1) % 200 == 0:
                elapsed = time.monotonic() - publish_start
                rate = (i + 1) / elapsed
                print(f"  Published {i + 1}/{count} ({rate:.0f} ev/s)")

        publish_elapsed = time.monotonic() - publish_start
        publish_rate = count / publish_elapsed
        print(f"\n✓ All {count} published in {publish_elapsed:.2f}s ({publish_rate:.0f} ev/s)")

    print("\nWaiting for backend to drain (timeout 60s)...\n")
    target = events_before + count
    drain_start = time.monotonic()
    while time.monotonic() - drain_start < 60:
        current = await count_events()
        elapsed = time.monotonic() - drain_start
        progress = current - events_before
        rate = progress / elapsed if elapsed > 0 else 0
        print(f"  In DB: {current}/{target} (+{progress}, {rate:.0f} ev/s, {elapsed:.1f}s)")
        if current >= target:
            break
        await asyncio.sleep(0.5)

    final = await count_events()
    total = time.monotonic() - publish_start

    print("\n" + "=" * 50)
    print("RESULTS")
    print("=" * 50)
    print(f"Events sent:       {count}")
    print(f"Events in DB:      {final - events_before}")
    if final - events_before < count:
        print(f"  ⚠ MISSING:       {count - (final - events_before)}")
    print(f"Total time:        {total:.2f}s")
    print(f"E2E throughput:    {(final - events_before) / total:.0f} ev/s")
    print(f"Publish-only rate: {publish_rate:.0f} ev/s")


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    try:
        asyncio.run(main(count))
    except KeyboardInterrupt:
        print("\n^C — прервано")
