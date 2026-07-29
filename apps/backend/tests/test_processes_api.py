"""Тесты эндпоинтов processes (supervisor-блок).

Покрытие:
- GET /processes: 401, 403, 200, фильтры line_id/station_id
- POST /processes: 401, 403, 201 happy, 404×2 (line/station), 409 (чужая линия),
  422×2 (одинаковые входы, выход=вход)
- PATCH /processes/{id}: 404, 200 частичное, 409 (станок с чужой линии), 422
- DELETE /processes/{id}: 404, 204
- GET /processes/topology/{line_id}: 404, 200 — уровни/рёбра/листья/warnings

Стиль как в test_shifts.py: собственные фикстуры с ручным cleanup,
реальная dev-БД. Для изоляции топологии каждая фикстура создаёт СВОЮ
линию — чужие процессы в неё не попадают.
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
from solvix_chronometry.models.processes import Process

# === Fixtures ===


async def _create_line_with_stations(n_stations: int) -> tuple[UUID, list[UUID]]:
    """Своя линия + N станков на ней. Возвращает (line_id, [station_ids])."""
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
            mac = f"04:{unique[0:2]}:{unique[2:4]}:{unique[4:6]}:{i:02x}:00"
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
            await session.execute(delete(Process).where(Process.line_id == line_id))
            await session.execute(delete(Station).where(Station.line_id == line_id))
            await session.execute(delete(Line).where(Line.id == line_id))


@pytest_asyncio.fixture
async def test_line() -> AsyncIterator[tuple[UUID, list[UUID]]]:
    """Линия с 4 станками (пилотная схема)."""
    line_id, station_ids = await _create_line_with_stations(4)
    try:
        yield line_id, station_ids
    finally:
        await _delete_line(line_id)


@pytest_asyncio.fixture
async def other_line() -> AsyncIterator[tuple[UUID, list[UUID]]]:
    """Вторая линия с 1 станком — для проверки «станок с чужой линии»."""
    line_id, station_ids = await _create_line_with_stations(1)
    try:
        yield line_id, station_ids
    finally:
        await _delete_line(line_id)


@pytest_asyncio.fixture
async def cleanup_processes() -> AsyncIterator[list[UUID]]:
    """Тест дописывает id созданных через API процессов — фикстура удалит."""
    ids: list[UUID] = []
    yield ids
    if ids:
        async with SessionLocal() as session:
            async with session.begin():
                await session.execute(delete(Process).where(Process.id.in_(ids)))


def _payload(line_id: UUID, station_id: UUID, **over) -> dict:
    body = {
        "line_id": str(line_id),
        "input_type_1": "A",
        "input_type_2": "B",
        "output_type": "C",
        "station_hint": str(station_id),
        "nominal_duration_sec": 120,
        "anomaly_threshold_pct": 30,
    }
    body.update(over)
    return body


# === Auth ===


@pytest.mark.asyncio
async def test_list_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/processes")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_forbidden_for_warehouse(warehouse_client: AsyncClient):
    resp = await warehouse_client.get("/api/v1/processes")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_requires_auth(client: AsyncClient, test_line):
    line_id, stations = test_line
    resp = await client.post(
        "/api/v1/processes", json=_payload(line_id, stations[0])
    )
    assert resp.status_code == 401


# === POST /processes ===


@pytest.mark.asyncio
async def test_create_process_happy(
    supervisor_client: AsyncClient, test_line, cleanup_processes
):
    line_id, stations = test_line
    resp = await supervisor_client.post(
        "/api/v1/processes", json=_payload(line_id, stations[0])
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    cleanup_processes.append(UUID(data["id"]))

    assert data["line_id"] == str(line_id)
    assert data["input_type_1"] == "A"
    assert data["input_type_2"] == "B"
    assert data["output_type"] == "C"
    assert data["station_hint"] == str(stations[0])
    assert data["nominal_duration_sec"] == 120
    assert data["valid_from"] is not None


@pytest.mark.asyncio
async def test_create_process_line_not_found(
    supervisor_client: AsyncClient, test_line
):
    _, stations = test_line
    resp = await supervisor_client.post(
        "/api/v1/processes", json=_payload(uuid4(), stations[0])
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_process_station_not_found(
    supervisor_client: AsyncClient, test_line
):
    line_id, _ = test_line
    resp = await supervisor_client.post(
        "/api/v1/processes", json=_payload(line_id, uuid4())
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_process_station_from_other_line(
    supervisor_client: AsyncClient, test_line, other_line
):
    line_id, _ = test_line
    _, other_stations = other_line
    resp = await supervisor_client.post(
        "/api/v1/processes", json=_payload(line_id, other_stations[0])
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_process_same_inputs_rejected(
    supervisor_client: AsyncClient, test_line
):
    line_id, stations = test_line
    resp = await supervisor_client.post(
        "/api/v1/processes",
        json=_payload(line_id, stations[0], input_type_1="A", input_type_2="A"),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_process_output_equals_input_rejected(
    supervisor_client: AsyncClient, test_line
):
    line_id, stations = test_line
    resp = await supervisor_client.post(
        "/api/v1/processes",
        json=_payload(line_id, stations[0], output_type="A"),
    )
    assert resp.status_code == 422


# === GET /processes (список + фильтры) ===


@pytest.mark.asyncio
async def test_list_filter_by_line(
    supervisor_client: AsyncClient, test_line, other_line, cleanup_processes
):
    line_id, stations = test_line
    other_id, other_stations = other_line

    r1 = await supervisor_client.post(
        "/api/v1/processes", json=_payload(line_id, stations[0])
    )
    r2 = await supervisor_client.post(
        "/api/v1/processes",
        json=_payload(other_id, other_stations[0], output_type="Z"),
    )
    assert r1.status_code == 201 and r2.status_code == 201
    cleanup_processes.extend([UUID(r1.json()["id"]), UUID(r2.json()["id"])])

    resp = await supervisor_client.get(
        "/api/v1/processes", params={"line_id": str(line_id)}
    )
    assert resp.status_code == 200
    ids = {p["id"] for p in resp.json()}
    assert r1.json()["id"] in ids
    assert r2.json()["id"] not in ids


@pytest.mark.asyncio
async def test_list_filter_by_station(
    supervisor_client: AsyncClient, test_line, cleanup_processes
):
    line_id, stations = test_line
    r1 = await supervisor_client.post(
        "/api/v1/processes", json=_payload(line_id, stations[0])
    )
    r2 = await supervisor_client.post(
        "/api/v1/processes",
        json=_payload(
            line_id, stations[1], input_type_1="D", input_type_2="E", output_type="F"
        ),
    )
    cleanup_processes.extend([UUID(r1.json()["id"]), UUID(r2.json()["id"])])

    resp = await supervisor_client.get(
        "/api/v1/processes", params={"station_id": str(stations[0])}
    )
    assert resp.status_code == 200
    ids = {p["id"] for p in resp.json()}
    assert r1.json()["id"] in ids
    assert r2.json()["id"] not in ids


# === PATCH /processes/{id} ===


@pytest.mark.asyncio
async def test_patch_not_found(supervisor_client: AsyncClient):
    resp = await supervisor_client.patch(
        f"/api/v1/processes/{uuid4()}", json={"nominal_duration_sec": 99}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_partial_update(
    supervisor_client: AsyncClient, test_line, cleanup_processes
):
    line_id, stations = test_line
    created = await supervisor_client.post(
        "/api/v1/processes", json=_payload(line_id, stations[0])
    )
    pid = created.json()["id"]
    cleanup_processes.append(UUID(pid))

    resp = await supervisor_client.patch(
        f"/api/v1/processes/{pid}", json={"nominal_duration_sec": 300}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["nominal_duration_sec"] == 300
    # Остальные поля не тронуты.
    assert data["input_type_1"] == "A"
    assert data["output_type"] == "C"
    assert data["station_hint"] == str(stations[0])


@pytest.mark.asyncio
async def test_patch_station_from_other_line_rejected(
    supervisor_client: AsyncClient, test_line, other_line, cleanup_processes
):
    line_id, stations = test_line
    _, other_stations = other_line
    created = await supervisor_client.post(
        "/api/v1/processes", json=_payload(line_id, stations[0])
    )
    pid = created.json()["id"]
    cleanup_processes.append(UUID(pid))

    resp = await supervisor_client.patch(
        f"/api/v1/processes/{pid}",
        json={"station_hint": str(other_stations[0])},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_patch_same_inputs_rejected(
    supervisor_client: AsyncClient, test_line, cleanup_processes
):
    line_id, stations = test_line
    created = await supervisor_client.post(
        "/api/v1/processes", json=_payload(line_id, stations[0])
    )
    pid = created.json()["id"]
    cleanup_processes.append(UUID(pid))

    # input_type_2 станет "A" — совпадёт с существующим input_type_1.
    resp = await supervisor_client.patch(
        f"/api/v1/processes/{pid}", json={"input_type_2": "A"}
    )
    assert resp.status_code == 422


# === DELETE /processes/{id} ===


@pytest.mark.asyncio
async def test_delete_not_found(supervisor_client: AsyncClient):
    resp = await supervisor_client.delete(f"/api/v1/processes/{uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_process(supervisor_client: AsyncClient, test_line):
    line_id, stations = test_line
    created = await supervisor_client.post(
        "/api/v1/processes", json=_payload(line_id, stations[0])
    )
    pid = created.json()["id"]

    resp = await supervisor_client.delete(f"/api/v1/processes/{pid}")
    assert resp.status_code == 204

    # Действительно удалён.
    listed = await supervisor_client.get(
        "/api/v1/processes", params={"line_id": str(line_id)}
    )
    assert pid not in {p["id"] for p in listed.json()}


# === GET /processes/topology/{line_id} ===


@pytest.mark.asyncio
async def test_topology_line_not_found(supervisor_client: AsyncClient):
    resp = await supervisor_client.get(f"/api/v1/processes/topology/{uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_topology_pyramid_end_to_end(
    supervisor_client: AsyncClient, test_line, cleanup_processes
):
    """Сквозной путь: справочник через API → корректная пирамида в ответе.

    Пилотная схема: st1(A+B→C), st2(D+E→F), st3(C+F→H), st4(H+G→ИЗД).
    """
    line_id, st = test_line
    rows = [
        _payload(line_id, st[0]),
        _payload(line_id, st[1], input_type_1="D", input_type_2="E", output_type="F"),
        _payload(line_id, st[2], input_type_1="C", input_type_2="F", output_type="H"),
        _payload(line_id, st[3], input_type_1="H", input_type_2="G", output_type="ИЗД"),
    ]
    for row in rows:
        r = await supervisor_client.post("/api/v1/processes", json=row)
        assert r.status_code == 201, r.text
        cleanup_processes.append(UUID(r.json()["id"]))

    resp = await supervisor_client.get(f"/api/v1/processes/topology/{line_id}")
    assert resp.status_code == 200, resp.text
    topo = resp.json()

    assert topo["line_id"] == str(line_id)
    assert len(topo["nodes"]) == 4
    assert topo["max_level"] == 2
    assert topo["warnings"] == []
    assert topo["base_part_types"] == ["A", "B", "D", "E", "G"]
    assert topo["final_output_types"] == ["ИЗД"]

    by_station = {n["station_id"]: n for n in topo["nodes"]}
    assert by_station[str(st[0])]["level"] == 0
    assert by_station[str(st[1])]["level"] == 0
    assert by_station[str(st[2])]["level"] == 1
    assert by_station[str(st[3])]["level"] == 2

    st3 = by_station[str(st[2])]
    assert set(st3["fed_by"]) == {str(st[0]), str(st[1])}
    assert st3["feeds_into"] == [str(st[3])]


@pytest.mark.asyncio
async def test_topology_idle_stations_warning(
    supervisor_client: AsyncClient, test_line, cleanup_processes
):
    """Станки линии без операций попадают в warnings."""
    line_id, st = test_line
    r = await supervisor_client.post(
        "/api/v1/processes", json=_payload(line_id, st[0])
    )
    cleanup_processes.append(UUID(r.json()["id"]))

    resp = await supervisor_client.get(f"/api/v1/processes/topology/{line_id}")
    assert resp.status_code == 200
    topo = resp.json()

    assert len(topo["nodes"]) == 1
    assert any("без операций" in w for w in topo["warnings"])


@pytest.mark.asyncio
async def test_topology_empty_line(supervisor_client: AsyncClient, test_line):
    """Линия без операций — пустая топология, не ошибка."""
    line_id, _ = test_line
    resp = await supervisor_client.get(f"/api/v1/processes/topology/{line_id}")
    assert resp.status_code == 200
    topo = resp.json()
    assert topo["nodes"] == []
    assert topo["max_level"] == 0
