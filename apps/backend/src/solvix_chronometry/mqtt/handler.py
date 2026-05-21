"""MQTT event handler — writes parsed StationEvent payloads to the events table.

Idempotent by design: dedup happens via PK (UUID v7 from terminal) using
INSERT ... ON CONFLICT DO NOTHING. Re-delivering the same event is a no-op.
See Решение №78 (QoS 1 + UUID v7 → effectively exactly-once).
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.models.events import Event
from solvix_chronometry.models.people import Shift
from solvix_chronometry.mqtt.schemas import StationEvent

logger = logging.getLogger(__name__)


async def handle_station_event(event: StationEvent, session: AsyncSession) -> None:
    """Process one parsed MQTT event from a terminal.

    1. Resolves the active shift on the source station (None if no one is logged in).
    2. INSERTs into events with ON CONFLICT DO NOTHING — duplicate deliveries
       (same UUID v7 from terminal) are silently skipped.
    """
    # Find latest active shift on this station (None if no one is bound)
    shift_stmt = (
        select(Shift.id)
        .where(Shift.station_id == event.station_id)
        .where(Shift.unbound_at.is_(None))
        .order_by(Shift.bound_at.desc())
        .limit(1)
    )
    shift_id = (await session.execute(shift_stmt)).scalar_one_or_none()

    # Idempotent INSERT — PK conflict means we've already stored this event
    stmt = (
        pg_insert(Event)
        .values(
            id=event.id,
            station_id=event.station_id,
            shift_id=shift_id,
            timestamp=event.timestamp,
            received_at=datetime.now(timezone.utc),
            event_type=event.event_type,
            part_id=event.part_id,
            details=event.details,
        )
        .on_conflict_do_nothing(index_elements=["id"])
        .returning(Event.id)
    )
    result = await session.execute(stmt)
    inserted_id = result.scalar_one_or_none()
    await session.commit()

    if inserted_id is None:
        logger.debug("event %s already exists, skipped", event.id)
    else:
        logger.info(
            "event stored: id=%s station=%s type=%s",
            event.id, event.station_id, event.event_type,
        )
