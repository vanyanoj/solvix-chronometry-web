"""Тесты эндпоинтов поиска (supervisor-блок)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from solvix_chronometry.db import SessionLocal
from solvix_chronometry.models.enums import PartStatus, UserRole
from solvix_chronometry.models.parts import Batch, Part
from solvix_chronometry.models.people import User


@pytest_asyncio.fixture
async def temp_part_set() -> AsyncIterator[list[str]]:
    """Создать batch + 3 part'а с разными статусами/типами для тестов."""
    batch_id: UUID | None = None
    part_ids: list[str] = []
    try:
        async with SessionLocal() as session:
            batch = Batch(part_type="SRCH")
            session.add(batch)
            await session.flush()
            batch_id = batch.id

            unique = uuid4().hex[:6]
            specs = [
                (f"SRCH-{unique}-001.0", "A", PartStatus.active),
                (f"SRCH-{unique}-002.0", "A", PartStatus.pending),
                (f"SRCH-{unique}-003.0", "B", PartStatus.active),
            ]
            for pid, ptype, pstatus in specs:
                p = Part(
                    id=pid,
                    base_id=pid.rsplit(".", 1)[0],
                    version=0,
                    type=ptype,
                    status=pstatus,
                    parents=[],
                    batch_id=batch.id,
                )
                session.add(p)
                part_ids.append(pid)
            await session.commit()
        yield part_ids
    finally:
        async with SessionLocal() as session:
            async with session.begin():
                if part_ids:
                    await session.execute(delete(Part).where(Part.id.in_(part_ids)))
                if batch_id:
                    await session.execute(delete(Batch).where(Batch.id == batch_id))


# === SEARCH USERS ===

async def test_search_users_no_token_returns_401(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/search/users")).status_code == 401


async def test_search_users_warehouse_forbidden(warehouse_client: AsyncClient) -> None:
    assert (await warehouse_client.get("/api/v1/search/users")).status_code == 403


async def test_search_users_no_q_returns_all(supervisor_client: AsyncClient) -> None:
    """Без q — возвращает всех (с лимитом)."""
    r = await supervisor_client.get("/api/v1/search/users?limit=100")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) >= 1  # хотя бы supervisor сам


async def test_search_users_by_substring(
    supervisor_client: AsyncClient, supervisor_user: User
) -> None:
    """Поиск по подстроке ФИО находит запись."""
    # Берём первое слово из имени supervisor для подстроки
    needle = supervisor_user.full_name.split()[0][:4]
    r = await supervisor_client.get(f"/api/v1/search/users?q={needle}&limit=100")
    assert r.status_code == 200
    ids = [it["id"] for it in r.json()]
    assert str(supervisor_user.id) in ids


async def test_search_users_filter_by_role(supervisor_client: AsyncClient) -> None:
    """Фильтр по роли."""
    r = await supervisor_client.get("/api/v1/search/users?role=supervisor&limit=100")
    assert r.status_code == 200
    for item in r.json():
        assert item["role"] == "supervisor"


async def test_search_users_pagination_validation(supervisor_client: AsyncClient) -> None:
    assert (await supervisor_client.get("/api/v1/search/users?limit=0")).status_code == 422
    assert (await supervisor_client.get("/api/v1/search/users?limit=200")).status_code == 422
    assert (await supervisor_client.get("/api/v1/search/users?offset=-1")).status_code == 422


async def test_search_users_response_structure(supervisor_client: AsyncClient) -> None:
    r = await supervisor_client.get("/api/v1/search/users?limit=1")
    if r.json():
        item = r.json()[0]
        assert set(item.keys()) == {"id", "full_name", "role", "active"}
        # pass_code не должен утекать
        assert "pass_code" not in item


# === SEARCH PARTS ===

async def test_search_parts_no_token_returns_401(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/search/parts")).status_code == 401


async def test_search_parts_warehouse_forbidden(warehouse_client: AsyncClient) -> None:
    assert (await warehouse_client.get("/api/v1/search/parts")).status_code == 403


async def test_search_parts_by_substring(
    supervisor_client: AsyncClient, temp_part_set: list[str]
) -> None:
    """Поиск по подстроке id находит нужные."""
    # Берём префикс общий для нашего набора
    prefix = temp_part_set[0].split("-")[1][:6]  # SRCH-XXXXXX-001.0 → XXXXXX
    r = await supervisor_client.get(f"/api/v1/search/parts?q={prefix}&limit=100")
    assert r.status_code == 200
    ids = {it["id"] for it in r.json()}
    for pid in temp_part_set:
        assert pid in ids


async def test_search_parts_filter_by_status(
    supervisor_client: AsyncClient, temp_part_set: list[str]
) -> None:
    """Фильтр по status=pending возвращает только pending детали."""
    prefix = temp_part_set[0].split("-")[1][:6]
    r = await supervisor_client.get(
        f"/api/v1/search/parts?q={prefix}&status=pending&limit=100"
    )
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1  # ровно одна pending в нашем наборе
    assert items[0]["status"] == "pending"


async def test_search_parts_filter_by_type(
    supervisor_client: AsyncClient, temp_part_set: list[str]
) -> None:
    """Фильтр по type=B возвращает только тип B."""
    prefix = temp_part_set[0].split("-")[1][:6]
    r = await supervisor_client.get(
        f"/api/v1/search/parts?q={prefix}&type=B&limit=100"
    )
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["type"] == "B"


async def test_search_parts_pagination_validation(supervisor_client: AsyncClient) -> None:
    assert (await supervisor_client.get("/api/v1/search/parts?limit=0")).status_code == 422
    assert (await supervisor_client.get("/api/v1/search/parts?limit=200")).status_code == 422
    assert (await supervisor_client.get("/api/v1/search/parts?offset=-1")).status_code == 422


async def test_search_parts_invalid_status_returns_422(supervisor_client: AsyncClient) -> None:
    r = await supervisor_client.get("/api/v1/search/parts?status=NONSENSE")
    assert r.status_code == 422


async def test_search_parts_response_structure(
    supervisor_client: AsyncClient, temp_part_set: list[str]
) -> None:
    prefix = temp_part_set[0].split("-")[1][:6]
    r = await supervisor_client.get(f"/api/v1/search/parts?q={prefix}&limit=1")
    item = r.json()[0]
    assert set(item.keys()) == {"id", "base_id", "version", "type", "status"}
