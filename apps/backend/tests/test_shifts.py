"""Тесты эндпоинтов shifts (supervisor-блок).

Покрытие POST /shifts: 401, 403, 404×3, 409 (не operator), 201 happy, 409×3 (занято)
Покрытие POST /shifts/{id}/force_close: 401, 403, 404, 200, 409 (уже закрыта)
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from solvix_chronometry.auth.hashing import hash_pass_code
from solvix_chronometry.db import SessionLocal
from solvix_chronometry.models.enums import UserRole
from solvix_chronometry.models.hierarchy import Line, Station
from solvix_chronometry.models.people import NfcBadge, Shift, User
from solvix_chronometry.uuid_v7 import uuid7

# === Fixtures ===

async def _create_test_station(name_suffix: str = "") -> tuple[UUID, str, str]:
    async with SessionLocal() as session:
        line = (await session.execute(select(Line).limit(1))).scalar_one_or_none()
        if line is None:
            raise RuntimeError("Нет Line в БД. Запусти scripts/seed_minimal.py.")
        unique = uuid4().hex[:8]
        name = f"TestStation-{unique[:6]}{name_suffix}"
        mac = f"02:{unique[0:2]}:{unique[2:4]}:{unique[4:6]}:00:00"
        station = Station(line_id=line.id, name=name, terminal_mac=mac)
        session.add(station)
        await session.commit()
        await session.refresh(station)
        return station.id, station.name, station.terminal_mac


async def _delete_test_station(station_id: UUID) -> None:
    async with SessionLocal() as session:
        async with session.begin():
            await session.execute(delete(Shift).where(Shift.station_id == station_id))
            await session.execute(delete(Station).where(Station.id == station_id))


@pytest_asyncio.fixture
async def test_station() -> AsyncIterator[Station]:
    sid, _, _ = await _create_test_station()
    async with SessionLocal() as session:
        station = (await session.execute(select(Station).where(Station.id == sid))).scalar_one()
    try:
        yield station
    finally:
        await _delete_test_station(sid)


@pytest_asyncio.fixture
async def test_station_2() -> AsyncIterator[Station]:
    sid, _, _ = await _create_test_station(name_suffix="-2")
    async with SessionLocal() as session:
        station = (await session.execute(select(Station).where(Station.id == sid))).scalar_one()
    try:
        yield station
    finally:
        await _delete_test_station(sid)


@pytest_asyncio.fixture
async def test_badge() -> AsyncIterator[NfcBadge]:
    badge_id: UUID | None = None
    try:
        async with SessionLocal() as session:
            badge = NfcBadge(uid=f"FIXT-UID-{uuid7().hex[:8]}")
            session.add(badge)
            await session.commit()
            await session.refresh(badge)
            badge_id = badge.id
        yield badge
    finally:
        if badge_id:
            async with SessionLocal() as session:
                async with session.begin():
                    await session.execute(delete(Shift).where(Shift.badge_id == badge_id))
                    await session.execute(delete(NfcBadge).where(NfcBadge.id == badge_id))


@pytest_asyncio.fixture
async def test_badge_2() -> AsyncIterator[NfcBadge]:
    badge_id: UUID | None = None
    try:
        async with SessionLocal() as session:
            badge = NfcBadge(uid=f"FIXT-UID2-{uuid7().hex[:8]}")
            session.add(badge)
            await session.commit()
            await session.refresh(badge)
            badge_id = badge.id
        yield badge
    finally:
        if badge_id:
            async with SessionLocal() as session:
                async with session.begin():
                    await session.execute(delete(Shift).where(Shift.badge_id == badge_id))
                    await session.execute(delete(NfcBadge).where(NfcBadge.id == badge_id))


@pytest_asyncio.fixture
async def cleanup_shifts() -> AsyncIterator[list[UUID]]:
    shift_ids: list[UUID] = []
    yield shift_ids
    if shift_ids:
        async with SessionLocal() as session:
            async with session.begin():
                await session.execute(delete(Shift).where(Shift.id.in_(shift_ids)))


@pytest_asyncio.fixture
async def active_shift(
    operator_user: User,
    test_badge: NfcBadge,
    test_station: Station,
) -> AsyncIterator[Shift]:
    """Активная смена (для тестов force_close)."""
    shift_id: UUID | None = None
    try:
        async with SessionLocal() as session:
            shift = Shift(
                user_id=operator_user.id,
                badge_id=test_badge.id,
                station_id=test_station.id,
            )
            session.add(shift)
            await session.commit()
            await session.refresh(shift)
            shift_id = shift.id
            shift_obj = shift
        yield shift_obj
    finally:
        if shift_id:
            async with SessionLocal() as session:
                async with session.begin():
                    await session.execute(delete(Shift).where(Shift.id == shift_id))


async def _create_extra_operator() -> UUID:
    async with SessionLocal() as session:
        u = User(
            pass_code_hash=hash_pass_code(f"FIXT-OPX-{uuid7().hex[:6]}"),
            full_name="Extra Operator",
            role=UserRole.operator,
            active=True,
        )
        session.add(u)
        await session.commit()
        await session.refresh(u)
        return u.id


async def _delete_user_with_shifts(user_id: UUID) -> None:
    async with SessionLocal() as session:
        async with session.begin():
            await session.execute(delete(Shift).where(Shift.user_id == user_id))
            await session.execute(delete(User).where(User.id == user_id))


# ============================================================================
# POST /shifts (создание)
# ============================================================================

async def test_no_token_returns_401(client: AsyncClient) -> None:
    r = await client.post("/api/v1/shifts", json={
        "user_id": str(uuid4()), "badge_id": str(uuid4()), "station_id": str(uuid4()),
    })
    assert r.status_code == 401


async def test_warehouse_role_forbidden(warehouse_client: AsyncClient) -> None:
    r = await warehouse_client.post("/api/v1/shifts", json={
        "user_id": str(uuid4()), "badge_id": str(uuid4()), "station_id": str(uuid4()),
    })
    assert r.status_code == 403


async def test_unknown_user_returns_404(
    supervisor_client: AsyncClient,
    test_badge: NfcBadge,
    test_station: Station,
) -> None:
    r = await supervisor_client.post("/api/v1/shifts", json={
        "user_id": str(uuid4()),
        "badge_id": str(test_badge.id),
        "station_id": str(test_station.id),
    })
    assert r.status_code == 404
    assert "user" in r.json()["detail"].lower()


async def test_unknown_badge_returns_404(
    supervisor_client: AsyncClient,
    operator_user: User,
    test_station: Station,
) -> None:
    r = await supervisor_client.post("/api/v1/shifts", json={
        "user_id": str(operator_user.id),
        "badge_id": str(uuid4()),
        "station_id": str(test_station.id),
    })
    assert r.status_code == 404
    assert "badge" in r.json()["detail"].lower()


async def test_unknown_station_returns_404(
    supervisor_client: AsyncClient,
    operator_user: User,
    test_badge: NfcBadge,
) -> None:
    r = await supervisor_client.post("/api/v1/shifts", json={
        "user_id": str(operator_user.id),
        "badge_id": str(test_badge.id),
        "station_id": str(uuid4()),
    })
    assert r.status_code == 404
    assert "station" in r.json()["detail"].lower()


async def test_non_operator_role_returns_409(
    supervisor_client: AsyncClient,
    warehouse_user: User,
    test_badge: NfcBadge,
    test_station: Station,
) -> None:
    r = await supervisor_client.post("/api/v1/shifts", json={
        "user_id": str(warehouse_user.id),
        "badge_id": str(test_badge.id),
        "station_id": str(test_station.id),
    })
    assert r.status_code == 409
    assert "operator" in r.json()["detail"].lower()


async def test_create_shift_happy_path(
    supervisor_client: AsyncClient,
    operator_user: User,
    test_badge: NfcBadge,
    test_station: Station,
    cleanup_shifts: list[UUID],
) -> None:
    r = await supervisor_client.post("/api/v1/shifts", json={
        "user_id": str(operator_user.id),
        "badge_id": str(test_badge.id),
        "station_id": str(test_station.id),
    })
    assert r.status_code == 201, r.text
    data = r.json()
    cleanup_shifts.append(UUID(data["id"]))

    assert data["user_id"] == str(operator_user.id)
    assert data["badge_id"] == str(test_badge.id)
    assert data["station_id"] == str(test_station.id)
    assert data["unbound_at"] is None
    assert data["closed_by"] is None


async def test_user_already_has_shift_returns_409(
    supervisor_client: AsyncClient,
    operator_user: User,
    test_badge: NfcBadge,
    test_badge_2: NfcBadge,
    test_station: Station,
    test_station_2: Station,
    cleanup_shifts: list[UUID],
) -> None:
    r1 = await supervisor_client.post("/api/v1/shifts", json={
        "user_id": str(operator_user.id),
        "badge_id": str(test_badge.id),
        "station_id": str(test_station.id),
    })
    assert r1.status_code == 201
    cleanup_shifts.append(UUID(r1.json()["id"]))

    r2 = await supervisor_client.post("/api/v1/shifts", json={
        "user_id": str(operator_user.id),
        "badge_id": str(test_badge_2.id),
        "station_id": str(test_station_2.id),
    })
    assert r2.status_code == 409
    assert "already has an active shift" in r2.json()["detail"].lower()


async def test_station_already_occupied_returns_409(
    supervisor_client: AsyncClient,
    operator_user: User,
    test_badge: NfcBadge,
    test_badge_2: NfcBadge,
    test_station: Station,
    cleanup_shifts: list[UUID],
) -> None:
    second_op_id: UUID | None = None
    try:
        second_op_id = await _create_extra_operator()
        r1 = await supervisor_client.post("/api/v1/shifts", json={
            "user_id": str(operator_user.id),
            "badge_id": str(test_badge.id),
            "station_id": str(test_station.id),
        })
        assert r1.status_code == 201
        cleanup_shifts.append(UUID(r1.json()["id"]))

        r2 = await supervisor_client.post("/api/v1/shifts", json={
            "user_id": str(second_op_id),
            "badge_id": str(test_badge_2.id),
            "station_id": str(test_station.id),
        })
        assert r2.status_code == 409
        assert "occupied" in r2.json()["detail"].lower()
    finally:
        if second_op_id:
            await _delete_user_with_shifts(second_op_id)


async def test_badge_already_in_use_returns_409(
    supervisor_client: AsyncClient,
    operator_user: User,
    test_badge: NfcBadge,
    test_station: Station,
    test_station_2: Station,
    cleanup_shifts: list[UUID],
) -> None:
    second_op_id: UUID | None = None
    try:
        second_op_id = await _create_extra_operator()
        r1 = await supervisor_client.post("/api/v1/shifts", json={
            "user_id": str(operator_user.id),
            "badge_id": str(test_badge.id),
            "station_id": str(test_station.id),
        })
        assert r1.status_code == 201
        cleanup_shifts.append(UUID(r1.json()["id"]))

        r2 = await supervisor_client.post("/api/v1/shifts", json={
            "user_id": str(second_op_id),
            "badge_id": str(test_badge.id),
            "station_id": str(test_station_2.id),
        })
        assert r2.status_code == 409
        assert "in use" in r2.json()["detail"].lower()
    finally:
        if second_op_id:
            await _delete_user_with_shifts(second_op_id)


# ============================================================================
# POST /shifts/{id}/force_close (закрытие)
# ============================================================================

async def test_force_close_no_token_returns_401(client: AsyncClient) -> None:
    r = await client.post(f"/api/v1/shifts/{uuid4()}/force_close")
    assert r.status_code == 401


async def test_force_close_warehouse_forbidden(warehouse_client: AsyncClient) -> None:
    r = await warehouse_client.post(f"/api/v1/shifts/{uuid4()}/force_close")
    assert r.status_code == 403


async def test_force_close_unknown_shift_returns_404(supervisor_client: AsyncClient) -> None:
    r = await supervisor_client.post(f"/api/v1/shifts/{uuid4()}/force_close")
    assert r.status_code == 404


async def test_force_close_active_shift_returns_200(
    supervisor_client: AsyncClient,
    active_shift: Shift,
) -> None:
    """Активная смена → 200, unbound_at заполнен, closed_by=supervisor."""
    r = await supervisor_client.post(f"/api/v1/shifts/{active_shift.id}/force_close")
    assert r.status_code == 200, r.text

    data = r.json()
    assert data["id"] == str(active_shift.id)
    assert data["unbound_at"] is not None
    assert data["closed_by"] == "supervisor"


async def test_force_close_already_closed_returns_409(
    supervisor_client: AsyncClient,
    active_shift: Shift,
) -> None:
    """Повторное закрытие уже закрытой смены → 409."""
    r1 = await supervisor_client.post(f"/api/v1/shifts/{active_shift.id}/force_close")
    assert r1.status_code == 200

    r2 = await supervisor_client.post(f"/api/v1/shifts/{active_shift.id}/force_close")
    assert r2.status_code == 409
    assert "already closed" in r2.json()["detail"].lower()


async def test_force_close_publishes_mqtt_command(
    supervisor_client: AsyncClient,
    active_shift: Shift,
    monkeypatch,
) -> None:
    """force_close публикует команду force_close_shift на терминал станка."""
    calls: list[tuple] = []

    async def fake_publish(station_id, command, params=None):
        calls.append((station_id, command, params))
        return "fake-command-id"

    monkeypatch.setattr(
        "solvix_chronometry.api.shifts.publish_command", fake_publish,
    )

    r = await supervisor_client.post(f"/api/v1/shifts/{active_shift.id}/force_close")
    assert r.status_code == 200, r.text

    assert len(calls) == 1
    station_id, command, params = calls[0]
    assert station_id == active_shift.station_id
    assert command == "force_close_shift"
    assert params == {"shift_id": str(active_shift.id)}


async def test_force_close_succeeds_when_mqtt_down(
    supervisor_client: AsyncClient,
    active_shift: Shift,
    monkeypatch,
) -> None:
    """Недоступный брокер не ломает закрытие смены (best-effort)."""

    async def broken_publish(*args, **kwargs):
        raise ConnectionError("broker down")

    monkeypatch.setattr(
        "solvix_chronometry.api.shifts.publish_command", broken_publish,
    )

    r = await supervisor_client.post(f"/api/v1/shifts/{active_shift.id}/force_close")
    assert r.status_code == 200, r.text
    assert r.json()["closed_by"] == "supervisor"
