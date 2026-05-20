"""Базовый класс моделей. SQLAlchemy 2.x typed Mapped[] style."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from solvix_chronometry.uuid_v7 import uuid7


class Base(DeclarativeBase):
    """База для всех моделей."""

    pass


def uuid7_pk() -> Mapped[uuid.UUID]:
    """Колонка-первичный-ключ UUID v7 с автогенерацией на стороне приложения.

    См. Решение №53: PK везде UUID v7 ради распределённой генерации
    (бэкенд + ESP32 + Central) без коллизий.
    """
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
    )


def created_at_col() -> Mapped[datetime]:
    """Стандартная колонка `created_at` (timestamp на стороне БД)."""
    return mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
