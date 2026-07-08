"""MQTT event handler — writes parsed StationEvent payloads to the events table.

Idempotent by design: dedup happens via PK (UUID v7 from terminal) using
INSERT ... ON CONFLICT DO NOTHING. Re-delivering the same event is a no-op.
See Решение №78 (QoS 1 + UUID v7 → effectively exactly-once).
"""
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.models.events import Event
from solvix_chronometry.models.people import Shift
from solvix_chronometry.mqtt.schemas import StationEvent
from solvix_chronometry.ws.hub import hub

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
            received_at=datetime.now(UTC),
            event_type=event.event_type,
            part_id=event.part_id,
            details=event.details,
        )
        .on_conflict_do_nothing(index_elements=["id"])
        .returning(Event.id)
    )
    try:
        result = await session.execute(stmt)
        inserted_id = result.scalar_one_or_none()
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        inserted_id = await _handle_fk_violation(event, session, shift_id, exc)
        if inserted_id is None:
            return

    if inserted_id is None:
        logger.info("event %s already exists, skipped (dedup)", event.id)
    else:
        logger.info(
            "event stored: id=%s station=%s type=%s",
            event.id, event.station_id, event.event_type,
        )
        # Real-time push фронтам (dashboard, в будущем — React)
        await hub.broadcast({
            "type": "event",
            "id": str(event.id),
            "station_id": str(event.station_id),
            "event_type": str(event.event_type),
            "timestamp": event.timestamp,
            "part_id": event.part_id,
        })


async def _handle_fk_violation(
    event: StationEvent,
    session: AsyncSession,
    shift_id,
    exc: IntegrityError,
):
    """FK-нарушение при вставке события — не терять молча (Логика работы:
    неизвестная деталь блокирует работу и должна быть видна, а не проглочена).

    - Неизвестный part_id → событие сохраняется с part_id=NULL и маркером
      в details (unknown_part) — след для watchdog/аналитики остаётся.
    - Неизвестный station_id → сохранить некуда (FK NOT NULL); терминал
      прислал событие с чужим/неведомым station_id — это ошибка конфигурации,
      логируем на уровне ERROR и дропаем.
    """
    cause = str(exc.orig)

    if "part_id" in cause:
        logger.error(
            "unknown part_id=%r in event %s from station %s — storing without FK",
            event.part_id, event.id, event.station_id,
        )
        details = dict(event.details or {})
        details["fk_violation"] = "unknown_part"
        details["unknown_part_id"] = event.part_id
        stmt = (
            pg_insert(Event)
            .values(
                id=event.id,
                station_id=event.station_id,
                shift_id=shift_id,
                timestamp=event.timestamp,
                received_at=datetime.now(UTC),
                event_type=event.event_type,
                part_id=None,
                details=details,
            )
            .on_conflict_do_nothing(index_elements=["id"])
            .returning(Event.id)
        )
        result = await session.execute(stmt)
        inserted_id = result.scalar_one_or_none()
        await session.commit()
        return inserted_id

    if "station_id" in cause:
        logger.error(
            "unknown station_id=%s in event %s — DROPPED. "
            "Terminal is misconfigured or station not registered.",
            event.station_id, event.id,
        )
        return None

    # прочие integrity-нарушения — не наш случай, пусть шумят как раньше
    raise exc
