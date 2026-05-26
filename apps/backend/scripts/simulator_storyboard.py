"""Storyboard-симулятор: режиссёрский сценарий цикла сборки.

Не случайный поток событий, а заскриптованный 80-секундный цикл:
- Деталь D-S1-A проходит S1 → S2 → S4 (норма наверху)
- Деталь D-S2-A проходит S3 (среднее)
- Параллельно: на S2 — норматив превышен (norm_exceeded)
- Параллельно: на S3 — оператор уходит на затянутый перекур (pause_exceeded)
- После 80 сек — replay

Запуск с WATCHDOG_DEMO_MODE=1 → watchdog тикает каждые 5 сек,
аномалии появляются в течение нескольких секунд после превышения порога.
"""
import asyncio
import json
import sys
from datetime import datetime, timezone

import aiomqtt
from sqlalchemy import select

from solvix_chronometry.config import settings
from solvix_chronometry.db import SessionLocal
from solvix_chronometry.models.break_reasons import BreakReason
from solvix_chronometry.models.hierarchy import Station
from solvix_chronometry.uuid_v7 import uuid7


async def fetch_setup():
    async with SessionLocal() as s:
        stations = list((await s.execute(
            select(Station).order_by(Station.name)
        )).scalars().all())
        smoke = (await s.execute(
            select(BreakReason).where(BreakReason.code == "smoke")
        )).scalar_one_or_none()
    return stations, smoke


async def emit(client, station_id, event_type, *, part_id=None, details=None):
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
    label = part_id or ""
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] {event_type:12s} station=...{station_id[-8:]} {label}")


async def play_one_cycle(client, s1, s2, s3, s4, smoke_id):
    """Один 80-секундный цикл сборки.

    Таймлайн:
      t=0:00  Старт
      t=0:03  S1: scan_in D-S1-A
      t=0:05  S1: start (Петров работает)
      t=0:11  S1: stop
      t=0:13  S1: scan_out (отгрузка наверх)
      t=0:15  S2: scan_in D-S1-A (Иванов принимает)
      t=0:17  S2: start (Иванов работает, начнётся медленно)
      t=0:20  S3: scan_in D-S2-A (параллельно — Сидоров принимает)
      t=0:22  S3: start
      t=0:25  S3: stop (Сидоров быстро отработал)
      t=0:27  S3: scan_out
      t=0:30  S3: break_start (перекур, лимит 30с)
      t=0:35  ⚠ watchdog видит: S2 операция уже 18 сек > 11 норматива → norm_exceeded
      t=0:50  S2: stop (Иванов наконец закончил, 33 сек реальное время)
      t=0:52  S2: scan_out
      t=0:55  S4: scan_in D-S1-A (Кузнецов принимает)
      t=0:57  S4: start
      t=1:00  ⚠ watchdog: пауза Сидорова уже 30 сек = порог; на следующем тике (1:05) >30 → pause_exceeded
      t=1:05  S4: stop
      t=1:07  S4: scan_out (финальная отгрузка)
      t=1:10  S3: break_end (Сидоров вернулся, но pause_exceeded уже зафиксирован)
      t=1:13  Пауза, все idle
      t=1:20  Reset
    """
    print("\n" + "─" * 60)
    print("Цикл сборки — старт")
    print("─" * 60)

    # === S1 (Вход) обрабатывает D-S1-A ===
    await asyncio.sleep(3)
    await emit(client, s1, "scan_in", part_id="D-S1-A")

    await asyncio.sleep(2)
    await emit(client, s1, "start", part_id="D-S1-A")

    await asyncio.sleep(6)
    await emit(client, s1, "stop", part_id="D-S1-A")

    await asyncio.sleep(2)
    await emit(client, s1, "scan_out", part_id="D-S1-A")

    # === S2 (Среднее) принимает D-S1-A — Иванов начнёт долгую операцию ===
    await asyncio.sleep(2)
    await emit(client, s2, "scan_in", part_id="D-S1-A")

    await asyncio.sleep(2)
    await emit(client, s2, "start", part_id="D-S1-A")
    print("  ⏳ S2: операция стартовала, норматив 10 сек — Иванов будет тянуть...")

    # === S3 (Среднее, параллельно) — Сидоров быстро отработал и уходит на перекур ===
    await asyncio.sleep(3)
    await emit(client, s3, "scan_in", part_id="D-S2-A")

    await asyncio.sleep(2)
    await emit(client, s3, "start", part_id="D-S2-A")

    await asyncio.sleep(3)
    await emit(client, s3, "stop", part_id="D-S2-A")

    await asyncio.sleep(2)
    await emit(client, s3, "scan_out", part_id="D-S2-A")

    await asyncio.sleep(3)
    await emit(client, s3, "break_start",
               details={"reason_id": smoke_id, "reason_code": "smoke"})
    print("  ⏳ S3: перекур стартовал, лимит 30 сек — Сидоров затянет...")

    # === S2 всё ещё работает — watchdog в это время поймает norm_exceeded ===
    # На текущий момент: S2 start был ~17 сек назад, нужно ещё ждать чтобы Иванов закрылся
    await asyncio.sleep(17)
    await emit(client, s2, "stop", part_id="D-S1-A")

    await asyncio.sleep(2)
    await emit(client, s2, "scan_out", part_id="D-S1-A")

    # === S4 (Выход) — финальная сборка ===
    await asyncio.sleep(3)
    await emit(client, s4, "scan_in", part_id="D-S1-A")

    await asyncio.sleep(2)
    await emit(client, s4, "start", part_id="D-S1-A")

    await asyncio.sleep(8)
    await emit(client, s4, "stop", part_id="D-S1-A")

    await asyncio.sleep(2)
    await emit(client, s4, "scan_out", part_id="D-S1-A")
    print("  ✓ S4: финальная отгрузка")

    # === S3: Сидоров вернулся — но уже поздно, pause_exceeded зафиксирован ===
    await asyncio.sleep(3)
    await emit(client, s3, "break_end")

    print("\n  ✓ Цикл завершён, пауза 10 сек перед replay\n")
    await asyncio.sleep(10)


async def main():
    stations, smoke = await fetch_setup()
    if len(stations) < 4:
        print("ERROR: нужно 4 станции. Запусти seed_demo_storyboard.py")
        sys.exit(1)
    if smoke is None:
        print("ERROR: нет break_reason 'smoke'. Запусти seed_demo_storyboard.py")
        sys.exit(1)

    s1, s2, s3, s4 = [str(s.id) for s in stations[:4]]
    smoke_id = str(smoke.id)

    print("=" * 60)
    print("STORYBOARD SIMULATOR")
    print("=" * 60)
    print(f"S1 (Вход)   : {stations[0].name}")
    print(f"S2 (Среднее): {stations[1].name}")
    print(f"S3 (Среднее): {stations[2].name}")
    print(f"S4 (Выход)  : {stations[3].name}")
    print(f"\nMQTT: {settings.mqtt_host}:{settings.mqtt_port}")

    async with aiomqtt.Client(settings.mqtt_host, port=settings.mqtt_port) as client:
        cycle = 1
        try:
            while True:
                print(f"\n{'#' * 60}")
                print(f"# ЦИКЛ #{cycle}")
                print(f"{'#' * 60}")
                await play_one_cycle(client, s1, s2, s3, s4, smoke_id)
                cycle += 1
        except asyncio.CancelledError:
            print("\nStopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped")
