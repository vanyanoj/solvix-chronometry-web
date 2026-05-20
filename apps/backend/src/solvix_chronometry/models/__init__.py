"""
Модели данных. Импорт всех таблиц здесь нужен в том числе для Alembic autogenerate
— чтобы `Base.metadata` видел все таблицы.
"""

from solvix_chronometry.models.base import Base
from solvix_chronometry.models.break_reasons import BreakReason
from solvix_chronometry.models.enums import (
    EventType,
    NfcBadgeStatus,
    PartStatus,
    ShiftClosedBy,
)
from solvix_chronometry.models.events import Event
from solvix_chronometry.models.hierarchy import Line, Site, Station, Workshop
from solvix_chronometry.models.parts import Batch, Part
from solvix_chronometry.models.people import NfcBadge, Shift, User
from solvix_chronometry.models.processes import Process

__all__ = [
    "Base",
    "Batch",
    "BreakReason",
    "Event",
    "EventType",
    "Line",
    "NfcBadge",
    "NfcBadgeStatus",
    "Part",
    "PartStatus",
    "Process",
    "Shift",
    "ShiftClosedBy",
    "Site",
    "Station",
    "User",
    "Workshop",
]
