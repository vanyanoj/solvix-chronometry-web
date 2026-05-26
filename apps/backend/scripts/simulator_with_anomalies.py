"""Симулятор с намеренными аномалиями для демки.

4 паттерна (по индексу станка):
- Station 1: норма — полный цикл scan_in → start → stop → scan_out (с part_id из DEMO partии)
- Station 2: norm_exceeded — start без последующего stop долго
- Station 3: pause_exceeded — break_start с reason_id, без break_end долго
- Station 4: transit_stuck — scan_out с part_id, без последующего scan_in

Запуск: WATCHDOG_DEMO_MODE=1 при старте бэка → watchdog ловит за 30 сек.
"""
import asyncio
import json
import random
import sys
from datetime import datetime, timezone

import aiomqtt
from sqlalchemy import select

from solvix_chronometry.config import settings
from solvix_chronometry.db import SessionLocal
from solvix_chronometry.models.break_reasons import BreakReason
from solvix_chronometry.models.hierarchy import Station
from solvix_chronometry.models.parts import Part
from solvix_chronometry.uuid_v7 import uuid7


async def fetch_demo_setup():
    """Загрузить станции, demo parts, и причину паузы для симуляции."""
    async with SessionLocal() as s:
        stations = list((await s.execute(select(Station).order_by(Station.name))).scalars().all())
        parts = list((await s.execute(
            select(Part).where(Part.id.like("DEMO-%"))
        )).scalars().all())
        smoke_reason = (await s.execute(
            select(BreakReason).where(BreakReason.code == "smoke")
        )).scalar_one_or_none()
    return stations, parts, smoke_reason


async def publish(client, station_id, event_type, part_id=None, details=None):
    payload = {
        "id": str(uuid7()),
        "station_id": station_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "part_id": part_id,
        "details": details,
    }
    await client.publish(
        f"solvix/station/{station_id}/event",
        payload=json.dumps(payload),
        qos=1,
    )
    print(f"  → {event_type:12s} on {station_id[-12:]} part={part_id}")


async def normal_cycle(client, station_id, station_name, part_id):
    """Станок 1: нормальный полный цикл."""
    print(f"[НОРМА] {station_name}")
    while True:
        await publish(client, station_id, "scan_in", part_id=part_id)
        await asyncio.sleep(random.uniform(1, 2))
        await publish(client, station_id, "start", part_id=part_id)
        await asyncio.sleep(random.uniform(4, 8))  # < 11с порога → норма
        await publish(client, station_id, "stop", part_id=part_id)
        await asyncio.sleep(random.uniform(0.5, 1.5))
        await publish(client, station_id, "scan_out", part_id=part_id)
        await asyncio.sleep(random.uniform(3, 6))


async def norm_exceeded_cycle(client, station_id, station_name, part_id):
    """Станок 2: операция тянется 60 сек > 11 сек норматива."""
    print(f"[АНОМАЛИЯ → norm_exceeded] {station_name}")
    while True:
        await publish(client, station_id, "scan_in", part_id=part_id)
        await asyncio.sleep(1.5)
        await publish(client, station_id, "start", part_id=part_id)
        await asyncio.sleep(70)  # >>> 11 сек норматива → norm_exceeded поймает
        await publish(client, station_id, "stop", part_id=part_id)
        await asyncio.sleep(2)
        await publish(client, station_id, "scan_out", part_id=part_id)
        await asyncio.sleep(8)


async def pause_exceeded_cycle(client, station_id, station_name, part_id, smoke_reason_id):
    """Станок 3: после start уходит на 'перекур' (порог 30с) дольше."""
    print(f"[АНОМАЛИЯ → pause_exceeded] {station_name}")
    while True:
        await publish(client, station_id, "scan_in", part_id=part_id)
        await asyncio.sleep(1.5)
        await publish(client, station_id, "start", part_id=part_id)
        await asyncio.sleep(3)
        await publish(client, station_id, "break_start", details={
            "reason_id": smoke_reason_id,
            "reason_code": "smoke",
        })
        await asyncio.sleep(45)  # >>> 30 сек порога → pause_exceeded поймает
        await publish(client, station_id, "break_end")
        await asyncio.sleep(2)
        await publish(client, station_id, "stop", part_id=part_id)
        await asyncio.sleep(2)
        await publish(client, station_id, "scan_out", part_id=part_id)
        await asyncio.sleep(8)


async def transit_stuck_cycle(client, station_id, station_name, part_id):
    """Станок 4: scan_out + долго ничего (нет scan_in где-либо с этим part_id)."""
    print(f"[АНОМАЛИЯ → transit_stuck] {station_name}")
    while True:
        await publish(client, station_id, "scan_in", part_id=part_id)
        await asyncio.sleep(1.5)
        await publish(client, station_id, "start", part_id=part_id)
        await asyncio.sleep(5)
        await publish(client, station_id, "stop", part_id=part_id)
        await asyncio.sleep(1.5)
        await publish(client, station_id, "scan_out", part_id=part_id)
        await asyncio.sleep(60)  # >>> 30 сек порога демки → transit_stuck поймает
        # Цикл начинается заново — но аномалия уже зафиксирована


async def main():
    stations, parts, smoke_reason = await fetch_demo_setup()
    if not stations or len(stations) < 4:
        print("ERROR: нужно минимум 4 станции. Запусти seed_minimal.py + seed_demo.py")
        sys.exit(1)
    if not parts or len(parts) < 4:
        print("ERROR: нет DEMO-parts. Запусти seed_demo_processes.py")
        sys.exit(1)
    if smoke_reason is None:
        print("ERROR: нет break_reason 'smoke'. Запусти seed_demo_processes.py")
        sys.exit(1)

    # Сортируем станции по имени, берём первые 4
    s1, s2, s3, s4 = stations[:4]
    p1, p2, p3, p4 = parts[:4]

    print("\n" + "=" * 60)
    print("Demo simulator — 3 типа аномалий")
    print("=" * 60)
    print(f"Connecting to MQTT at {settings.mqtt_host}:{settings.mqtt_port}\n")

    async with aiomqtt.Client(settings.mqtt_host, port=settings.mqtt_port) as client:
        tasks = [
            asyncio.create_task(normal_cycle(client, str(s1.id), s1.name, p1.id)),
            asyncio.create_task(norm_exceeded_cycle(client, str(s2.id), s2.name, p2.id)),
            asyncio.create_task(pause_exceeded_cycle(client, str(s3.id), s3.name, p3.id, str(smoke_reason.id))),
            asyncio.create_task(transit_stuck_cycle(client, str(s4.id), s4.name, p4.id)),
        ]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            print("\nShutting down")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped")
