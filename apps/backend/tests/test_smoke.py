"""Smoke-тесты — модели импортируются, UUID v7 валиден."""

from __future__ import annotations

import uuid

from solvix_chronometry.models import Base, Event, Part, Site
from solvix_chronometry.uuid_v7 import uuid7


def test_uuid7_is_valid_uuid() -> None:
    u = uuid7()
    assert isinstance(u, uuid.UUID)
    assert u.version == 7


def test_uuid7_is_time_ordered() -> None:
    import time

    a = uuid7()
    time.sleep(0.002)  # 2 мс — гарантируем разные timestamp-секции
    b = uuid7()
    # UUID v7 включает timestamp_ms в первые 48 бит → b > a как 128-битное число.
    # Внутри одной мс порядок случайный (rand_a / rand_b), это норм для RFC 9562.
    assert b.int > a.int


def test_metadata_contains_expected_tables() -> None:
    names = set(Base.metadata.tables.keys())
    expected = {
        "sites",
        "workshops",
        "lines",
        "stations",
        "parts",
        "batches",
        "processes",
        "users",
        "nfc_badges",
        "shifts",
        "break_reasons",
        "events",
    }
    missing = expected - names
    assert not missing, f"Не зарегистрированы таблицы: {missing}"


def test_models_export() -> None:
    assert Site.__tablename__ == "sites"
    assert Part.__tablename__ == "parts"
    assert Event.__tablename__ == "events"
