"""Симулятор: имитирует поток MQTT-событий от 4 терминалов.

Берёт станции из БД, запускает по asyncio-задаче на каждую.
Шлёт scan_in → start → stop → scan_out циклически со случайными интервалами.

Запуск: python scripts/simulator.py
Stop: Ctrl+C

NB: part_id в событиях пока null — для реальных part_id нужно сначала
засеять parts (отдельный шаг).
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
from solvix_chronometry.models.hierarchy import Station
from solvix_chronometry.uuid_v7 import uuid7


async def get_stations() -> list[Station]:
    async with SessionLocal() as s:
        return list((await s.execute(select(Station))).scalars().all())


async def publish_event(client: aiomqtt.Client, station_id: str, event_type: str) -> None:
    payload = {
        "id": str(uuid7()),
        "station_id": station_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "part_id": None,
        "details": None,
    }
    await client.publish(
        f"solvix/station/{station_id}/event",
        payload=json.dumps(payload),
        qos=1,
    )
    print(f"  → {event_type:10s} on station ...{station_id[-12:]}")


async def station_cycle(client: aiomqtt.Client, station_id: str, station_name: str) -> None:
    """Бесконечный цикл одного станка."""
    print(f"Started cycle for {station_name}")

    while True:
        # 1. Скан входящей
        await publish_event(client, station_id, "scan_in")
        await asyncio.sleep(random.uniform(1, 3))

        # 2. Старт работы
        await publish_event(client, station_id, "start")

        # 3. "Работа" — 10-25 сек
        await asyncio.sleep(random.uniform(10, 25))

        # 4. Стоп
        await publish_event(client, station_id, "stop")
        await asyncio.sleep(random.uniform(0.5, 2))

        # 5. Скан исходящей
        await publish_event(client, station_id, "scan_out")

        # 6. Пауза перед следующим циклом — 5-15 сек
        await asyncio.sleep(random.uniform(5, 15))


async def main() -> None:
    stations = await get_stations()
    if not stations:
        print("ERROR: нет станций в БД. Запусти seed_minimal.py + seed_demo.py")
        sys.exit(1)

    print(f"Found {len(stations)} stations:")
    for st in stations:
        print(f"  • {st.name} (id={st.id})")

    print(f"\nConnecting to MQTT at {settings.mqtt_host}:{settings.mqtt_port}")

    async with aiomqtt.Client(settings.mqtt_host, port=settings.mqtt_port) as client:
        print("Connected. Starting station cycles. Ctrl+C to stop.\n")

        tasks = [
            asyncio.create_task(station_cycle(client, str(st.id), st.name))
            for st in stations
        ]

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            print("\nCancelled, shutting down")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user")
