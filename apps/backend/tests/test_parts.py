"""Тесты эндпоинтов parts (warehouse-блок).

Покрытие:
- GET /parts/{id}: auth (401/403), 404 на несуществующую, 200 с деталью
- POST /parts/{id}/confirm: auth (401/403), 404, 200 pending→active,
  409 на already-active и на absorbed
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from solvix_chronometry.db import SessionLocal
from solvix_chronometry.models.enums import PartStatus
from solvix_chronometry.models.parts import Batch, Part
from solvix_chronometry.uuid_v7 import uuid7


# === Helpers ===

async def _create_test_part(part_status: PartStatus) -> tuple[Part, UUID, str]:
    """Создаёт batch + деталь в заданном статусе. Возвращает (part, batch_id, part_id)."""
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
            status=part_status,
            parents=[],
            batch_id=batch.id,
        )
        session.add(part)
        await session.commit()
        await session.refresh(part)
        return part, batch.id, part_id


async def _delete_test_part(part_id: str, batch_id: UUID) -> None:
    async with SessionLocal() as session:
        async with session.begin():
            await session.execute(delete(Part).where(Part.id == part_id))
            await session.execute(delete(Batch).where(Batch.id == batch_id))


# === Fixtures: одна на каждый статус ===

@pytest_asyncio.fixture
async def existing_part() -> AsyncIterator[Part]:
    """Pending-деталь — для GET и для confirm-200."""
    part, batch_id, part_id = await _create_test_part(PartStatus.pending)
    try:
        yield part
    finally:
        await _delete_test_part(part_id, batch_id)


@pytest_asyncio.fixture
async def existing_active_part() -> AsyncIterator[Part]:
    """Active-деталь — для теста повторного confirm (должен дать 409)."""
    part, batch_id, part_id = await _create_test_part(PartStatus.active)
    try:
        yield part
    finally:
        await _delete_test_part(part_id, batch_id)


@pytest_asyncio.fixture
async def existing_absorbed_part() -> AsyncIterator[Part]:
    """Absorbed-деталь — для теста confirm absorbed (должен дать 409)."""
    part, batch_id, part_id = await _create_test_part(PartStatus.absorbed)
    try:
        yield part
    finally:
        await _delete_test_part(part_id, batch_id)


# === GET /parts/{id} ===

async def test_get_no_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/parts/SOMETHING")
    assert response.status_code == 401


async def test_get_supervisor_role_forbidden(supervisor_client: AsyncClient) -> None:
    response = await supervisor_client.get("/api/v1/parts/SOMETHING")
    assert response.status_code == 403


async def test_get_unknown_part_returns_404(warehouse_client: AsyncClient) -> None:
    response = await warehouse_client.get("/api/v1/parts/NONEXISTENT-9999")
    assert response.status_code == 404


async def test_get_existing_part_returns_200(
    warehouse_client: AsyncClient,
    existing_part: Part,
) -> None:
    response = await warehouse_client.get(f"/api/v1/parts/{existing_part.id}")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["id"] == existing_part.id
    assert data["status"] == "pending"
    assert data["version"] == 0


# === POST /parts/{id}/confirm ===

async def test_confirm_no_token_returns_401(client: AsyncClient) -> None:
    response = await client.post("/api/v1/parts/SOMETHING/confirm")
    assert response.status_code == 401


async def test_confirm_supervisor_role_forbidden(supervisor_client: AsyncClient) -> None:
    response = await supervisor_client.post("/api/v1/parts/SOMETHING/confirm")
    assert response.status_code == 403


async def test_confirm_unknown_part_returns_404(warehouse_client: AsyncClient) -> None:
    response = await warehouse_client.post("/api/v1/parts/NONEXISTENT-9999/confirm")
    assert response.status_code == 404


async def test_confirm_pending_to_active(
    warehouse_client: AsyncClient,
    existing_part: Part,
) -> None:
    """Главный позитивный путь: pending → active."""
    assert existing_part.status == PartStatus.pending
    response = await warehouse_client.post(f"/api/v1/parts/{existing_part.id}/confirm")
    assert response.status_code == 200, response.text

    data = response.json()
    assert data["id"] == existing_part.id
    assert data["status"] == "active"


async def test_confirm_already_active_returns_409(
    warehouse_client: AsyncClient,
    existing_active_part: Part,
) -> None:
    """Повторный confirm уже подтверждённой детали → 409."""
    response = await warehouse_client.post(f"/api/v1/parts/{existing_active_part.id}/confirm")
    assert response.status_code == 409
    assert "already active" in response.json()["detail"].lower()


async def test_confirm_absorbed_returns_409(
    warehouse_client: AsyncClient,
    existing_absorbed_part: Part,
) -> None:
    """Confirm детали что уже ушла в сборку → 409."""
    response = await warehouse_client.post(f"/api/v1/parts/{existing_absorbed_part.id}/confirm")
    assert response.status_code == 409
    assert "absorbed" in response.json()["detail"].lower()
