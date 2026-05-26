"""Тесты эндпоинтов timeline (supervisor-блок)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from solvix_chronometry.db import SessionLocal
from solvix_chronometry.models.enums import EventType, NfcBadgeStatus, PartStatus
from solvix_chronometry.models.events import Event
from solvix_chronometry.models.hierarchy import Line, Station
from solvix_chronometry.models.parts import Batch, Part
from solvix_chronometry.models.people import NfcBadge, Shift, User


@pytest_asyncio.fixture
async def temp_station() -> AsyncIterator[Station]:
    sid: UUID | None = None
    try:
        async with SessionLocal() as session:
            line = (await session.execute(select(Line).limit(1))).scalar_one_or_none()
            if line is None:
                raise RuntimeError("Нет Line в БД.")
            unique = uuid4().hex[:8]
            st = Station(
                line_id=line.id,
                name=f"TimelineTest-{unique[:6]}",
                terminal_mac=f"02:{unique[0:2]}:{unique[2:4]}:{unique[4:6]}:33:33",
            )
            session.add(st)
            await session.commit()
            await session.refresh(st)
            sid = st.id
        async with SessionLocal() as session:
            yield (await session.execute(select(Station).where(Station.id == sid))).scalar_one()
    finally:
        if sid:
            async with SessionLocal() as session:
                async with session.begin():
                    await session.execute(delete(Event).where(Event.station_id == sid))
                    await session.execute(delete(Shift).where(Shift.station_id == sid))
                    await session.execute(delete(Station).where(Station.id == sid))


@pytest_asyncio.fixture
async def temp_part() -> AsyncIterator[str]:
    """Создать batch + 1 part."""
    batch_id: UUID | None = None
    part_id: str | None = None
    try:
        async with SessionLocal() as session:
            batch = Batch(part_type="TL")
            session.add(batch)
            await session.flush()
            batch_id = batch.id
            unique = uuid4().hex[:6]
            p = Part(
                id=f"TL-{unique}.0",
                base_id=f"TL-{unique}",
                version=0, type="A",
                status=PartStatus.active,
                parents=[],
                batch_id=batch.id,
            )
            session.add(p)
            await session.commit()
            part_id = p.id
        yield part_id
    finally:
        async with SessionLocal() as session:
            async with session.begin():
                if part_id:
                    await session.execute(delete(Event).where(Event.part_id == part_id))
                    await session.execute(delete(Part).where(Part.id == part_id))
                if batch_id:
                    await session.execute(delete(Batch).where(Batch.id == batch_id))


@pytest_asyncio.fixture
async def operator_with_shift(
    temp_station: Station, operator_user: User,
) -> AsyncIterator[Shift]:
    """Создать активную смену оператора на станке."""
    shift_id: UUID | None = None
    badge_id: UUID | None = None
    try:
        async with SessionLocal() as session:
            badge = NfcBadge(uid=f"TL-{uuid4().hex[:8]}", status=NfcBadgeStatus.bound)
            session.add(badge)
            await session.commit()
            await session.refresh(badge)
            badge_id = badge.id
            shift = Shift(
                user_id=operator_user.id,
                badge_id=badge.id,
                station_id=temp_station.id,
                bound_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
            session.add(shift)
            await session.commit()
            await session.refresh(shift)
            shift_id = shift.id
        async with SessionLocal() as session:
            yield (await session.execute(select(Shift).where(Shift.id == shift_id))).scalar_one()
    finally:
        async with SessionLocal() as session:
            async with session.begin():
                if shift_id:
                    await session.execute(delete(Event).where(Event.shift_id == shift_id))
                    await session.execute(delete(Shift).where(Shift.id == shift_id))
                if badge_id:
                    await session.execute(delete(NfcBadge).where(NfcBadge.id == badge_id))


async def _add_event(
    station_id: UUID, event_type: EventType, ts: datetime,
    part_id: str | None = None, shift_id: UUID | None = None,
) -> UUID:
    async with SessionLocal() as session:
        ev = Event(
            timestamp=ts, received_at=ts,
            station_id=station_id, event_type=event_type,
            part_id=part_id, shift_id=shift_id,
        )
        session.add(ev)
        await session.commit()
        await session.refresh(ev)
        return ev.id


# === PART TIMELINE ===

async def test_part_timeline_no_token_returns_401(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/parts/X/timeline")).status_code == 401


async def test_part_timeline_warehouse_forbidden(warehouse_client: AsyncClient) -> None:
    assert (await warehouse_client.get("/api/v1/parts/X/timeline")).status_code == 403


async def test_part_timeline_unknown_returns_404(supervisor_client: AsyncClient) -> None:
    r = await supervisor_client.get("/api/v1/parts/NOT-EXISTS-XYZ/timeline")
    assert r.status_code == 404


async def test_part_timeline_empty_for_new_part(
    supervisor_client: AsyncClient, temp_part: str,
) -> None:
    """Новая деталь без событий → пустой список."""
    r = await supervisor_client.get(f"/api/v1/parts/{temp_part}/timeline")
    assert r.status_code == 200
    assert r.json() == []


async def test_part_timeline_returns_events_chronologically(
    supervisor_client: AsyncClient, temp_part: str, temp_station: Station,
) -> None:
    """События должны быть отсортированы по timestamp ASC."""
    now = datetime.now(timezone.utc)
    e3 = await _add_event(temp_station.id, EventType.scan_out, now, part_id=temp_part)
    e1 = await _add_event(temp_station.id, EventType.scan_in, now - timedelta(seconds=20), part_id=temp_part)
    e2 = await _add_event(temp_station.id, EventType.start, now - timedelta(seconds=15), part_id=temp_part)

    r = await supervisor_client.get(f"/api/v1/parts/{temp_part}/timeline")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 3
    # Хронологический порядок
    assert items[0]["id"] == str(e1)
    assert items[1]["id"] == str(e2)
    assert items[2]["id"] == str(e3)
    # Структура и station_name через JOIN
    assert items[0]["station_name"] == temp_station.name
    assert items[0]["event_type"] == "scan_in"
    assert items[0]["part_id"] == temp_part


async def test_part_timeline_pagination_validation(
    supervisor_client: AsyncClient, temp_part: str,
) -> None:
    assert (await supervisor_client.get(f"/api/v1/parts/{temp_part}/timeline?limit=0")).status_code == 422
    assert (await supervisor_client.get(f"/api/v1/parts/{temp_part}/timeline?limit=1000")).status_code == 422
    assert (await supervisor_client.get(f"/api/v1/parts/{temp_part}/timeline?offset=-1")).status_code == 422


# === USER TIMELINE ===

async def test_user_timeline_no_token_returns_401(client: AsyncClient) -> None:
    assert (await client.get(f"/api/v1/users/{uuid4()}/timeline")).status_code == 401


async def test_user_timeline_warehouse_forbidden(warehouse_client: AsyncClient) -> None:
    assert (await warehouse_client.get(f"/api/v1/users/{uuid4()}/timeline")).status_code == 403


async def test_user_timeline_unknown_returns_404(supervisor_client: AsyncClient) -> None:
    r = await supervisor_client.get(f"/api/v1/users/{uuid4()}/timeline")
    assert r.status_code == 404


async def test_user_timeline_empty_without_events(
    supervisor_client: AsyncClient, operator_user: User,
) -> None:
    """У оператора без активных событий по сменам → пустой список (фильтруем по shift_id IS NOT NULL)."""
    r = await supervisor_client.get(f"/api/v1/users/{operator_user.id}/timeline?since=2030-01-01T00:00:00Z")
    assert r.status_code == 200
    assert r.json() == []


async def test_user_timeline_returns_events_via_shift(
    supervisor_client: AsyncClient,
    operator_user: User,
    operator_with_shift: Shift,
    temp_station: Station,
) -> None:
    """События со shift_id попадают в таймлайн оператора."""
    now = datetime.now(timezone.utc)
    e1 = await _add_event(
        temp_station.id, EventType.start, now - timedelta(seconds=10),
        shift_id=operator_with_shift.id,
    )
    e2 = await _add_event(
        temp_station.id, EventType.stop, now,
        shift_id=operator_with_shift.id,
    )

    r = await supervisor_client.get(f"/api/v1/users/{operator_user.id}/timeline?limit=200")
    assert r.status_code == 200
    items = r.json()
    ids = [it["id"] for it in items]
    assert str(e1) in ids
    assert str(e2) in ids
    # Хронологический
    idx1 = ids.index(str(e1))
    idx2 = ids.index(str(e2))
    assert idx1 < idx2


async def test_user_timeline_since_filter(
    supervisor_client: AsyncClient,
    operator_user: User,
    operator_with_shift: Shift,
    temp_station: Station,
) -> None:
    """Фильтр since исключает старые события."""
    now = datetime.now(timezone.utc)
    e_old = await _add_event(
        temp_station.id, EventType.start, now - timedelta(hours=2),
        shift_id=operator_with_shift.id,
    )
    e_new = await _add_event(
        temp_station.id, EventType.stop, now - timedelta(minutes=10),
        shift_id=operator_with_shift.id,
    )

    one_hour_ago = (now - timedelta(hours=1)).isoformat()
    r = await supervisor_client.get(
        f"/api/v1/users/{operator_user.id}/timeline",
        params={"since": one_hour_ago, "limit": 200},
    )
    assert r.status_code == 200
    ids = [it["id"] for it in r.json()]
    assert str(e_old) not in ids
    assert str(e_new) in ids


async def test_user_timeline_pagination_validation(
    supervisor_client: AsyncClient, operator_user: User,
) -> None:
    base = f"/api/v1/users/{operator_user.id}/timeline"
    assert (await supervisor_client.get(f"{base}?limit=0")).status_code == 422
    assert (await supervisor_client.get(f"{base}?limit=1000")).status_code == 422
    assert (await supervisor_client.get(f"{base}?offset=-1")).status_code == 422
