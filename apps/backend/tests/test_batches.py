"""Тесты эндпоинтов batches (warehouse-блок)."""

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
async def populated_batch() -> AsyncIterator[tuple[Batch, list[Part]]]:
    """
    Batch с уникальным part_type + 5 деталей в разных статусах:
    2 pending, 2 active, 1 absorbed. Уникальный part_type чтобы найти
    нашу партию в списке среди возможных других.
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


async def test_no_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/batches")
    assert response.status_code == 401


async def test_supervisor_role_forbidden(supervisor_client: AsyncClient) -> None:
    response = await supervisor_client.get("/api/v1/batches")
    assert response.status_code == 403


async def test_basic_list_returns_200(warehouse_client: AsyncClient) -> None:
    """Базовый запрос → 200 и массив (даже если пусто)."""
    response = await warehouse_client.get("/api/v1/batches")
    assert response.status_code == 200, response.text
    assert isinstance(response.json(), list)


async def test_pagination_validation(warehouse_client: AsyncClient) -> None:
    """limit и offset вне диапазона → 422 от FastAPI-валидации."""
    assert (await warehouse_client.get("/api/v1/batches?limit=0")).status_code == 422
    assert (await warehouse_client.get("/api/v1/batches?limit=500")).status_code == 422
    assert (await warehouse_client.get("/api/v1/batches?offset=-1")).status_code == 422


async def test_status_counts_correct(
    warehouse_client: AsyncClient,
    populated_batch: tuple[Batch, list[Part]],
) -> None:
    """Партия с 2 pending + 2 active + 1 absorbed → правильные счётчики."""
    batch, _ = populated_batch

    # Берём limit побольше чтобы наша партия точно попала
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
