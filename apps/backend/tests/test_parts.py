"""Тесты эндпоинтов parts (warehouse-блок).

Покрытие: без токена → 401, неправильная роль → 403, несуществующая деталь → 404,
существующая деталь → 200 с полным response.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from solvix_chronometry.db import SessionLocal
from solvix_chronometry.models.enums import PartStatus
from solvix_chronometry.models.parts import Batch, Part
from solvix_chronometry.uuid_v7 import uuid7


@pytest_asyncio.fixture
async def existing_part() -> AsyncIterator[Part]:
    """Создаёт временную batch + одну pending-деталь, удаляет после теста."""
    unique = uuid7().hex[:8]
    part_id = f"TEST-{unique}"

    async with SessionLocal() as session:
        batch = Batch(part_type="TEST")
        session.add(batch)
        await session.commit()
        await session.refresh(batch)

        part = Part(
            id=part_id,
            base_id=part_id,
            version=0,
            type="TEST",
            status=PartStatus.pending,
            parents=[],
            batch_id=batch.id,
        )
        session.add(part)
        await session.commit()
        await session.refresh(part)
        batch_id = batch.id

    yield part

    async with SessionLocal() as session:
        async with session.begin():
            await session.execute(delete(Part).where(Part.id == part_id))
            await session.execute(delete(Batch).where(Batch.id == batch_id))


async def test_no_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/parts/SOMETHING")
    assert response.status_code == 401


async def test_supervisor_role_forbidden(supervisor_client: AsyncClient) -> None:
    """По Решению №84 /parts — warehouse-блок. Supervisor получает 403."""
    response = await supervisor_client.get("/api/v1/parts/SOMETHING")
    assert response.status_code == 403


async def test_unknown_part_returns_404(warehouse_client: AsyncClient) -> None:
    response = await warehouse_client.get("/api/v1/parts/NONEXISTENT-9999")
    assert response.status_code == 404


async def test_existing_part_returns_200(
    warehouse_client: AsyncClient,
    existing_part: Part,
) -> None:
    response = await warehouse_client.get(f"/api/v1/parts/{existing_part.id}")
    assert response.status_code == 200, response.text

    data = response.json()
    assert data["id"] == existing_part.id
    assert data["base_id"] == existing_part.base_id
    assert data["version"] == 0
    assert data["type"] == "TEST"
    assert data["status"] == "pending"
    assert data["parents"] == []
    assert "batch_id" in data
    assert "created_at" in data
