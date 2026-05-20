"""
`parts` и `batches` — детали и партии приёмки.

Ключевая особенность `parts`: id — строковый композит `base_id` + версия,
например `D-0001` (исходная) → `D-0001.1` (после первой сборки) → `D-0001.2`.
См. Решения №3-6 (QR-наследование).

`parents` — массив FK на `parts.id` родителей: при сборке `A-0001 + B-0001 → A-0001.1`
у новой записи parents = [A-0001, B-0001].
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from solvix_chronometry.models.base import Base, created_at_col, uuid7_pk
from solvix_chronometry.models.enums import PartStatus


class Batch(Base):
    """Партия приёмки — минимальная (см. Решение №33)."""

    __tablename__ = "batches"

    id: Mapped[uuid.UUID] = uuid7_pk()
    part_type: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = created_at_col()


class Part(Base):
    """
    Деталь / её версия. PK — строковый композит.

    Базовые детали (A, B, D, E) появляются при печати наклейки кладовщиком (`pending`)
    и переходят в `active` при подтверждающем скане. Производные (C, F, H…) появляются
    в момент сборки на станке сразу как `active`.
    """

    __tablename__ = "parts"

    # ID — строка, например `D-0001` или `D-0001.2`. См. Логика работы → раздел 4.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    # Физическая наклейка: то что напечатано на детали. Не меняется при сборке.
    base_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Версия: 0 = исходная от кладовщика, 1+ = после каждой операции.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Тип (A, B, C, D, …).
    type: Mapped[str] = mapped_column(String(50), nullable=False)

    status: Mapped[PartStatus] = mapped_column(nullable=False, default=PartStatus.pending)

    # Родители: массив FK на parts.id. Пусто для исходных, [parent1, parent2] для производных.
    # ForeignKey на элементы массива в Postgres не enforced — целостность проверяется логикой.
    parents: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)),
        nullable=False,
        default=list,
    )

    created_at: Mapped[datetime] = created_at_col()

    # На каком станке создана эта версия (null у исходных).
    station_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stations.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # Какая NFC-сессия активна в момент создания (null у исходных).
    shift_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shifts.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # Партия приёмки, в которой деталь появилась.
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=False,
    )
