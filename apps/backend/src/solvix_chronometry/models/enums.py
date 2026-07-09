"""
Енумы, общие для нескольких таблиц.

Используем `native_enum=True` (Postgres native ENUM), чтобы получить
типобезопасность на уровне БД и видеть значения в `psql` напрямую.
"""

from __future__ import annotations

import enum


class PartStatus(str, enum.Enum):
    """Жизненный цикл детали (см. Логика работы → раздел 3)."""

    pending = "pending"      # QR напечатан, кладовщик ещё не подтвердил
    active = "active"        # деталь в системе, скан-активна
    absorbed = "absorbed"    # поглощена при сборке, скан-неактивна


class NfcBadgeStatus(str, enum.Enum):
    """Состояние NFC-бейджа в пуле распределителя."""

    free = "free"
    bound = "bound"
    lost = "lost"


class ShiftClosedBy(str, enum.Enum):
    """Кто закрыл смену (см. Решения №36-37)."""

    self_ = "self"             # сотрудник сам, своим бейджем
    supervisor = "supervisor"  # старший принудительно


class EventType(str, enum.Enum):
    """Типы событий сканов и состояний терминала.

    См. Модель данных → events. Включает `anomaly` (Решение №66) —
    конкретный вид аномалии хранится в `details.kind`:
    norm_exceeded / transit_stuck / pause_exceeded / station_idle.
    """

    scan_in = "scan_in"          # скан входящей детали
    start = "start"              # СТАРТ
    stop = "stop"                # СТОП (явный или неявный)
    scan_out = "scan_out"        # скан исходящей детали
    break_start = "break_start"  # начало паузы
    break_end = "break_end"      # конец паузы
    error = "error"              # ошибка (неизвестная деталь, поглощённая, нет пары)
    interrupted = "interrupted"  # операция прервана, закрыта старшим
    anomaly = "anomaly"          # зафиксированная аномалия (вид — в details.kind)


class UserRole(str, enum.Enum):
    """Роль пользователя — для JWT-авторизации и аудита (Решение №83).

    Старший смены выполняет роль распределителя (bind/unbind NFC-бейджей)
    в дополнение к наблюдению за дашбордом.
    """

    warehouse = "warehouse"      # кладовщик
    supervisor = "supervisor"    # старший смены (дашборд + bind/unbind бейджей)
    operator = "operator"        # оператор станка

