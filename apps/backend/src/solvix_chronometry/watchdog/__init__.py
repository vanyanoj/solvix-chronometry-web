"""Watchdog — фоновый детектор аномалий.

См. Обсидиан → Решения №62-70 (виды аномалий и пороги) и Логика работы.

Виды аномалий (этапы 2-5):
- `norm_exceeded`   — операция превысила норматив (этап 2)
- `pause_exceeded`  — пауза дольше порога break_reasons.max_duration_sec (этап 3)
- `station_idle`    — активная смена без событий N минут (этап 4)
- `transit_stuck`   — деталь застряла между станками (этап 5)
"""

from solvix_chronometry.core.anomalies import create_anomaly_event
from solvix_chronometry.watchdog.runner import run_watchdog

__all__ = ["create_anomaly_event", "run_watchdog"]
