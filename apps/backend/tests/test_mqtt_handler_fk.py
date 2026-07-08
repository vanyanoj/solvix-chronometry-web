"""MQTT handler: FK-нарушения не должны терять события молча.

- Неизвестный part_id → событие сохраняется с part_id=NULL + маркер в details.
- Неизвестный station_id → событие дропается с ERROR-логом, без исключения.
- Валидное событие — как раньше (регресс).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select, text

from solvix_chronometry.db import SessionLocal
from solvix_chronometry.models.events import Event
from solvix_chronometry.mqtt.handler import handle_station_event
from solvix_chronometry.mqtt.schemas import StationEvent
from solvix_chronometry.uuid_v7 import uuid7

pytestmark = pytest.mark.asyncio


async def _existing_station_id():
    async with SessionLocal() as session:
        return (await session.execute(text("SELECT id FROM stations LIMIT 1"))).scalar()


def _event(station_id, part_id=None, details=None) -> StationEvent:
    return StationEvent(
        id=uuid7(),
        station_id=station_id,
        timestamp=datetime.now(UTC).isoformat(),
        event_type="scan_in",
        part_id=part_id,
        details=details,
    )


async def _fetch_and_cleanup(event_id):
    async with SessionLocal() as session:
        row = (await session.execute(
            select(Event).where(Event.id == event_id)
        )).scalar_one_or_none()
        if row is not None:
            await session.execute(delete(Event).where(Event.id == event_id))
            await session.commit()
        return row


async def test_unknown_part_preserved_with_marker():
    station_id = await _existing_station_id()
    ev = _event(station_id, part_id="GHOST-9999", details={"src": "test"})

    async with SessionLocal() as session:
        await handle_station_event(ev, session)

    stored = await _fetch_and_cleanup(ev.id)
    assert stored is not None, "event with unknown part must be preserved"
    assert stored.part_id is None
    assert stored.details["fk_violation"] == "unknown_part"
    assert stored.details["unknown_part_id"] == "GHOST-9999"
    assert stored.details["src"] == "test"  # исходные details не потеряны


async def test_unknown_station_dropped_without_exception(caplog):
    ev = _event(uuid7())  # станции с таким id нет

    with caplog.at_level(logging.ERROR):
        async with SessionLocal() as session:
            await handle_station_event(ev, session)  # не должно бросить

    assert any("unknown station_id" in r.message for r in caplog.records)
    stored = await _fetch_and_cleanup(ev.id)
    assert stored is None


async def test_valid_event_still_stored():
    station_id = await _existing_station_id()
    ev = _event(station_id)

    async with SessionLocal() as session:
        await handle_station_event(ev, session)

    stored = await _fetch_and_cleanup(ev.id)
    assert stored is not None
    assert stored.part_id is None
    assert stored.station_id == station_id
