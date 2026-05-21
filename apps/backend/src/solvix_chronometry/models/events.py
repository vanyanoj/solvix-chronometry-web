"""
`events` — события сканов и состояний. **Самая важная таблица системы**:
из неё считается весь хронометраж и аномалии.

Решение №53 (UUID v7) + архитектурный документ:
> Поле `device_event_id` сливается с `events.id` — один первичный ключ.
ESP32 генерирует UUID v7 локально при возникновении события, кладёт в NVS-буфер,
шлёт серверу. Глобальная уникальность → дедупликация бесплатно по PK.

`details` (JSONB) хранит:
- для `error`: причину (`unknown_part`, `absorbed_part`, `no_process`)
- для `break_start`/`break_end`: `{"reason_id": ..., "reason_code": "lunch"}`
- для `anomaly`: `{"kind": "norm_exceeded" | "transit_stuck" | "pause_exceeded" | "station_idle", ...}`
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from solvix_chronometry.models.base import Base, uuid7_pk
from solvix_chronometry.models.enums import EventType


class Event(Base):
    __tablename__ = "events"

    # UUID v7 — генерируется на терминале при возникновении события.
    # Уникальность глобальная, дедупликация по PK.
    id: Mapped[uuid.UUID] = uuid7_pk()

    # Время события по часам терминала.
    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, index=True
    )

    # Когда сервер принял событие. Различие с `timestamp` показывает буферизованные/задержанные.
    received_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    shift_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shifts.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    event_type: Mapped[EventType] = mapped_column(nullable=False, index=True)

    # Если событие связано с конкретной деталью (scan_in / scan_out).
    part_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("parts.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # Структурированные детали — см. docstring модуля.
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
