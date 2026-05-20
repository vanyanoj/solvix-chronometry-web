"""
`users`, `nfc_badges`, `shifts` — люди и сессии.

Бейджи **не персональные** (пул у распределителя, Решение №10).
`shifts` — bind-сессии: связь сотрудник ↔ бейдж ↔ станок на время смены.
Закрытие смены — только своим бейджем (Решения №36-38), принудительно — только старший.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from solvix_chronometry.models.base import Base, uuid7_pk
from solvix_chronometry.models.enums import NfcBadgeStatus, ShiftClosedBy


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid7_pk()
    pass_code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class NfcBadge(Base):
    __tablename__ = "nfc_badges"

    id: Mapped[uuid.UUID] = uuid7_pk()
    uid: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    status: Mapped[NfcBadgeStatus] = mapped_column(
        nullable=False, default=NfcBadgeStatus.free
    )


class Shift(Base):
    __tablename__ = "shifts"

    id: Mapped[uuid.UUID] = uuid7_pk()

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    badge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("nfc_badges.id", ondelete="RESTRICT"), nullable=False
    )
    station_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stations.id", ondelete="SET NULL"),
        nullable=True,
    )

    bound_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    unbound_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    # null пока смена идёт, после закрытия — кто закрыл (self / supervisor).
    closed_by: Mapped[ShiftClosedBy | None] = mapped_column(nullable=True)
