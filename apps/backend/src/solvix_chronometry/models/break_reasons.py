"""
`break_reasons` — справочник причин пауз.

Раньше причины были enum'ом. После Решения №68 — отдельная таблица,
чтобы у каждой причины был свой `max_duration_sec` (порог аномалии паузы).

Контент при инициализации: обед / перекур / туалет / другое.
Технолог в будущем правит пороги руками через интерфейс.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from solvix_chronometry.models.base import Base, uuid7_pk


class BreakReason(Base):
    __tablename__ = "break_reasons"

    id: Mapped[uuid.UUID] = uuid7_pk()
    code: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    max_duration_sec: Mapped[int] = mapped_column(Integer, nullable=False)
