"""
Иерархия: Site → Workshop → Line → Station.

См. Решение №52 и Модель данных → Иерархия.
На пилоте: 1 site, 1 workshop, 1 line, 4 stations.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from solvix_chronometry.models.base import Base, created_at_col, uuid7_pk


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[uuid.UUID] = uuid7_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = created_at_col()

    workshops: Mapped[list["Workshop"]] = relationship(back_populates="site")


class Workshop(Base):
    __tablename__ = "workshops"

    id: Mapped[uuid.UUID] = uuid7_pk()
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    site: Mapped["Site"] = relationship(back_populates="workshops")
    lines: Mapped[list["Line"]] = relationship(back_populates="workshop")


class Line(Base):
    __tablename__ = "lines"

    id: Mapped[uuid.UUID] = uuid7_pk()
    workshop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workshops.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    topology: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = created_at_col()

    workshop: Mapped["Workshop"] = relationship(back_populates="lines")
    stations: Mapped[list["Station"]] = relationship(back_populates="line")


class Station(Base):
    __tablename__ = "stations"

    id: Mapped[uuid.UUID] = uuid7_pk()
    line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lines.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    terminal_mac: Mapped[str] = mapped_column(String(17), nullable=False, unique=True)

    line: Mapped["Line"] = relationship(back_populates="stations")
