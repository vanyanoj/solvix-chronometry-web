"""
`processes` — справочник процессов: какие пары входящих деталей дают какой результат.

Версионирование через `valid_from` (см. Решения №34-35): при изменении норматива
технологом добавляется новая строка с новым `valid_from`. Старые операции остаются
со своим нормативом на момент выполнения.

`anomaly_threshold_pct` — порог аномалии превышения норматива (см. Решение №63).

`line_id` — на какой линии выполняется операция (Решение №85: изделие = линия).
Топология пирамиды выводится из этого справочника (Решение №86).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from solvix_chronometry.models.base import Base, uuid7_pk


class Process(Base):
    __tablename__ = "processes"

    id: Mapped[uuid.UUID] = uuid7_pk()

    # Линия = сборочный поток = изделие (Решение №85). Nullable ради
    # обратной совместимости с уже засеянными строками; заполняется при
    # бэкфилле через станок и требуется для попадания в топологию.
    line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lines.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    input_type_1: Mapped[str] = mapped_column(String(50), nullable=False)
    input_type_2: Mapped[str] = mapped_column(String(50), nullable=False)
    output_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Где выполняется. Исторически «hint» (Решение №13), но для топологии
    # обязателен: без него узел не строится (Решение №87).
    station_hint: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Нормативное время операции в секундах.
    nominal_duration_sec: Mapped[int] = mapped_column(Integer, nullable=False)

    # Порог аномалии: % сверх норматива. Дефолт 30%. Решение №63.
    anomaly_threshold_pct: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=30,
        server_default="30",
    )

    # С какого момента действует эта запись. При расчёте аномалии берётся запись
    # с максимальным valid_from ≤ timestamp события.
    valid_from: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
