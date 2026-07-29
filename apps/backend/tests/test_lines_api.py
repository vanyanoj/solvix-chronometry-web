"""Тесты эндпоинтов lines (supervisor-блок).

Покрытие:
- GET /lines: 401, 403, 200, корректность сводных счётчиков
  (station_count / active_station_count / process_count / has_topology)
- GET /lines/{id}: 404, 200

Счётчики — три GROUP BY-запроса с джойнами, самое вероятное место ошибки,
поэтому проверяются на подготовленных данных с известными ответами.

Стиль как в test_shifts.py / test_processes_api.py: собственные фикстуры,
реальная dev-БД, ручной cleanup.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from solvix_chronometry.db import SessionLocal
from solvix_chronometry.models.hierarchy import Line, Station, Workshop
from solvix_chronometry.models.people import NfcBadge, Shift, User
from solvix_chronometry.models.processes import Process
from solvix_chronometry.uuid_v7 import uuid7

# === Fixtures ===


async def _create_line_with_stations(n_stations: int) -> tuple[UUID, list[UUID]]:
    unique = uuid4().hex[:8]
    async with SessionLocal() as session:
        workshop = (
            await session.execute(select(Workshop).limit(1))
        ).scalar_one_or_none()
        if workshop is None:
            raise RuntimeError("Нет Workshop в БД. Запусти scripts/seed_minimal.py.")
        line = Line(workshop_id=workshop.id, name=f"TestLine-{unique}")
        session.add(line)
        await session.flush()
        stations = []
        for i in range(n_stations):
            mac = f"06:{unique[0:2]}:{unique[2:4]}:{unique[4:6]}:{i:02x}:00"
            st = Station(
                line_id=line.id,
                name=f"TL-{unique[:4]}-St{i + 1}",
                terminal_mac=mac,
            )
            session.add(st)
            stations.append(st)
        await session.commit()
        return line.id, [st.id for st in stations]


async def _delete_line(line_id: UUID) -> None:
    async with SessionLocal() as session:
        async with session.begin():
            station_ids = (
                await session.execute(
                    select(Station.id).where(Station.line_id == line_id)
                )
            ).scalars().all()
            if station_ids:
                await session.execute(
                    delete(Shift).where(Shift.station_id.in_(station_ids))
                )
            await session.execute(delete(Process).where(Process.line_id == line_id))
            await session.execute(delete(Station).where(Station.line_id == line_id))
            await session.execute(delete(Line).where(Line.id == line_id))


@pytest_asyncio.fixture
async def test_line() -> AsyncIterator[tuple[UUID, list[UUID]]]:
    """Линия с 3 станками."""
    line_id, station_ids = await _create_line_with_stations(3)
    try:
        yield line_id, station_ids
    finally:
        await _delete_line(line_id)


@pytest_asyncio.fixture
async def empty_line() -> AsyncIterator[UUID]:
    """Линия вообще без станков."""
    line_id, _ = await _create_line_with_stations(0)
    try:
        yield line_id
    finally:
        await _delete_line(line_id)


@pytest_asyncio.fixture
async def occupied_station(
    test_line, operator_user: User
) -> AsyncIterator[UUID]:
    """Активная смена на первом станке линии: 1 занятый станок из 3.

    Свой бейдж, свой Shift — cleanup в finally (Shift дополнительно
    страхуется в _delete_line, но бейдж чистим здесь).
    """
    _, station_ids = test_line
    badge_id: UUID | None = None
    shift_id: UUID | None = None
    try:
        async with SessionLocal() as session:
            badge = NfcBadge(uid=f"FIXT-LINES-{uuid7().hex[:8]}")
            session.add(badge)
            await session.flush()
            badge_id = badge.id
            shift = Shift(
                user_id=operator_user.id,
                badge_id=badge.id,
                station_id=station_ids[0],
            )
            session.add(shift)
            await session.commit()
            shift_id = shift.id
        yield station_ids[0]
    finally:
        async with SessionLocal() as session:
            async with session.begin():
                if shift_id:
                    await session.execute(delete(Shift).where(Shift.id == shift_id))
                if badge_id:
                    await session.execute(
                        delete(NfcBadge).where(NfcBadge.id == badge_id)
                    )


async def _add_process(
    line_id: UUID,
    station_id: UUID | None,
    input_1: str = "A",
    input_2: str = "B",
    output: str = "C",
) -> UUID:
    async with SessionLocal() as session:
        p = Process(
            line_id=line_id,
            input_type_1=input_1,
            input_type_2=input_2,
            output_type=output,
            station_hint=station_id,
            nominal_duration_sec=120,
        )
        session.add(p)
        await session.commit()
        await session.refresh(p)
        return p.id


def _line_from(resp_json: list[dict], line_id: UUID) -> dict:
    match = [row for row in resp_json if row["id"] == str(line_id)]
    assert match, f"Линия {line_id} не найдена в ответе"
    return match[0]


# === Auth ===


@pytest.mark.asyncio
async def test_list_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/lines")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_forbidden_for_warehouse(warehouse_client: AsyncClient):
    resp = await warehouse_client.get("/api/v1/lines")
    assert resp.status_code == 403


# === GET /lines ===


@pytest.mark.asyncio
async def test_list_counts_stations(supervisor_client: AsyncClient, test_line):
    line_id, station_ids = test_line
    resp = await supervisor_client.get("/api/v1/lines")
    assert resp.status_code == 200, resp.text

    row = _line_from(resp.json(), line_id)
    assert row["station_count"] == len(station_ids)
    assert row["active_station_count"] == 0
    assert row["process_count"] == 0
    assert row["has_topology"] is False


@pytest.mark.asyncio
async def test_list_counts_active_stations(
    supervisor_client: AsyncClient, test_line, occupied_station
):
    line_id, _ = test_line
    resp = await supervisor_client.get("/api/v1/lines")

    row = _line_from(resp.json(), line_id)
    assert row["station_count"] == 3
    assert row["active_station_count"] == 1


@pytest.mark.asyncio
async def test_list_counts_processes_and_topology_flag(
    supervisor_client: AsyncClient, test_line
):
    line_id, station_ids = test_line

    # Один процесс без станка: count растёт, топологии всё ещё нет.
    await _add_process(line_id, None)
    resp = await supervisor_client.get("/api/v1/lines")
    row = _line_from(resp.json(), line_id)
    assert row["process_count"] == 1
    assert row["has_topology"] is False

    # Процесс со станком: появляется топология.
    await _add_process(line_id, station_ids[0], "D", "E", "F")
    resp = await supervisor_client.get("/api/v1/lines")
    row = _line_from(resp.json(), line_id)
    assert row["process_count"] == 2
    assert row["has_topology"] is True


@pytest.mark.asyncio
async def test_list_line_without_stations(
    supervisor_client: AsyncClient, empty_line
):
    """Линия без станков не роняет группировки — нули, а не отсутствие."""
    resp = await supervisor_client.get("/api/v1/lines")
    assert resp.status_code == 200

    row = _line_from(resp.json(), empty_line)
    assert row["station_count"] == 0
    assert row["active_station_count"] == 0
    assert row["process_count"] == 0
    assert row["has_topology"] is False


@pytest.mark.asyncio
async def test_list_counts_are_per_line(
    supervisor_client: AsyncClient, test_line, empty_line
):
    """Счётчики не перетекают между линиями."""
    line_id, station_ids = test_line
    await _add_process(line_id, station_ids[0])

    resp = await supervisor_client.get("/api/v1/lines")
    data = resp.json()

    busy = _line_from(data, line_id)
    empty = _line_from(data, empty_line)
    assert busy["process_count"] == 1
    assert empty["process_count"] == 0
    assert busy["station_count"] == 3
    assert empty["station_count"] == 0


# === GET /lines/{id} ===


@pytest.mark.asyncio
async def test_get_line_not_found(supervisor_client: AsyncClient):
    resp = await supervisor_client.get(f"/api/v1/lines/{uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_line_detail(
    supervisor_client: AsyncClient, test_line, occupied_station
):
    line_id, station_ids = test_line
    await _add_process(line_id, station_ids[0])

    resp = await supervisor_client.get(f"/api/v1/lines/{line_id}")
    assert resp.status_code == 200, resp.text
    row = resp.json()

    assert row["id"] == str(line_id)
    assert row["station_count"] == 3
    assert row["active_station_count"] == 1
    assert row["process_count"] == 1
    assert row["has_topology"] is True
