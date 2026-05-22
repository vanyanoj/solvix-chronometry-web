"""Тесты эндпоинтов batches (warehouse-блок).

Покрытие:
- GET /batches: auth (401/403), базовый 200, валидация пагинации, счётчики статусов
- GET /batches/{id}: auth (401/403), 404 на несуществующую, 200 с полным детализом
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from solvix_chronometry.db import SessionLocal
from solvix_chronometry.models.enums import PartStatus
from solvix_chronometry.models.parts import Batch, Part
from solvix_chronometry.uuid_v7 import uuid7


@pytest_asyncio.fixture
async def populated_batch() -> AsyncIterator[tuple[Batch, list[Part]]]:
    """
    Batch с уникальным part_type + 5 деталей в разных статусах:
    2 pending, 2 active, 1 absorbed.
    """
    unique_type = f"FIXT-{uuid7().hex[:8]}"

    async with SessionLocal() as session:
        batch = Batch(part_type=unique_type)
        session.add(batch)
        await session.commit()
        await session.refresh(batch)
        batch_id = batch.id

        parts: list[Part] = []
        statuses = [
            PartStatus.pending, PartStatus.pending,
            PartStatus.active, PartStatus.active,
            PartStatus.absorbed,
        ]
        for i, st in enumerate(statuses):
            part_id = f"{unique_type}-{i:04d}"
            part = Part(
                id=part_id,
                base_id=part_id,
                version=0,
                type=unique_type,
                status=st,
                parents=[],
                batch_id=batch_id,
            )
            session.add(part)
            parts.append(part)
        await session.commit()
        for p in parts:
            await session.refresh(p)
        part_ids = [p.id for p in parts]

    yield batch, parts

    async with SessionLocal() as session:
        async with session.begin():
            for pid in part_ids:
                await session.execute(delete(Part).where(Part.id == pid))
            await session.execute(delete(Batch).where(Batch.id == batch_id))


# === GET /batches (list) ===

async def test_list_no_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/batches")
    assert response.status_code == 401


async def test_list_supervisor_role_forbidden(supervisor_client: AsyncClient) -> None:
    response = await supervisor_client.get("/api/v1/batches")
    assert response.status_code == 403


async def test_list_basic_returns_200(warehouse_client: AsyncClient) -> None:
    response = await warehouse_client.get("/api/v1/batches")
    assert response.status_code == 200, response.text
    assert isinstance(response.json(), list)


async def test_list_pagination_validation(warehouse_client: AsyncClient) -> None:
    assert (await warehouse_client.get("/api/v1/batches?limit=0")).status_code == 422
    assert (await warehouse_client.get("/api/v1/batches?limit=500")).status_code == 422
    assert (await warehouse_client.get("/api/v1/batches?offset=-1")).status_code == 422


async def test_list_status_counts_correct(
    warehouse_client: AsyncClient,
    populated_batch: tuple[Batch, list[Part]],
) -> None:
    batch, _ = populated_batch
    response = await warehouse_client.get("/api/v1/batches?limit=200")
    assert response.status_code == 200

    items = response.json()
    our = next((item for item in items if item["id"] == str(batch.id)), None)
    assert our is not None, f"Партия {batch.id} не найдена в ответе"

    assert our["part_type"] == batch.part_type
    assert our["total_parts"] == 5
    assert our["pending_count"] == 2
    assert our["active_count"] == 2
    assert our["absorbed_count"] == 1


# === GET /batches/{id} (detail) ===

async def test_detail_no_token_returns_401(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/batches/{uuid4()}")
    assert response.status_code == 401


async def test_detail_supervisor_role_forbidden(supervisor_client: AsyncClient) -> None:
    response = await supervisor_client.get(f"/api/v1/batches/{uuid4()}")
    assert response.status_code == 403


async def test_detail_unknown_batch_returns_404(warehouse_client: AsyncClient) -> None:
    response = await warehouse_client.get(f"/api/v1/batches/{uuid4()}")
    assert response.status_code == 404


async def test_detail_returns_batch_with_all_parts(
    warehouse_client: AsyncClient,
    populated_batch: tuple[Batch, list[Part]],
) -> None:
    """Запрос конкретной партии возвращает её метаданные + все 5 деталей."""
    batch, parts = populated_batch
    response = await warehouse_client.get(f"/api/v1/batches/{batch.id}")
    assert response.status_code == 200, response.text

    data = response.json()
    assert data["id"] == str(batch.id)
    assert data["part_type"] == batch.part_type
    assert "created_at" in data

    returned_parts = data["parts"]
    assert len(returned_parts) == 5

    statuses = sorted(p["status"] for p in returned_parts)
    assert statuses == ["absorbed", "active", "active", "pending", "pending"]

    # Проверим одну деталь полностью — все ожидаемые поля
    sample = returned_parts[0]
    expected_keys = {"id", "base_id", "version", "status", "parents",
                     "station_id", "shift_id", "created_at"}
    assert set(sample.keys()) == expected_keys
