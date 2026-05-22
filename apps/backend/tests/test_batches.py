"""Тесты эндпоинтов batches (warehouse-блок).

Покрытие:
- GET /batches: auth (401/403), 200, пагинация, счётчики статусов
- GET /batches/{id}: auth (401/403), 404, 200 с полным детализом
- POST /batches: auth (401/403), 422 (валидация), 201 happy path,
  201 авто-нумерация продолжается между партиями
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from solvix_chronometry.db import SessionLocal
from solvix_chronometry.models.enums import PartStatus
from solvix_chronometry.models.parts import Batch, Part
from solvix_chronometry.uuid_v7 import uuid7


@pytest_asyncio.fixture
async def populated_batch() -> AsyncIterator[tuple[Batch, list[Part]]]:
    """Batch с 5 деталями: 2 pending + 2 active + 1 absorbed."""
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
            pid = f"{unique_type}-{i:04d}"
            p = Part(
                id=pid, base_id=pid, version=0, type=unique_type,
                status=st, parents=[], batch_id=batch_id,
            )
            session.add(p)
            parts.append(p)
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


@pytest_asyncio.fixture
async def cleanup_batches() -> AsyncIterator[list[UUID]]:
    """Yield пустой список. Тест докидывает туда batch.id созданных
    через API. В teardown удаляются ВСЕ parts+batches по этим id."""
    batch_ids: list[UUID] = []
    yield batch_ids

    if batch_ids:
        async with SessionLocal() as session:
            async with session.begin():
                await session.execute(delete(Part).where(Part.batch_id.in_(batch_ids)))
                await session.execute(delete(Batch).where(Batch.id.in_(batch_ids)))


# === GET /batches (list) ===

async def test_list_no_token_returns_401(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/batches")).status_code == 401


async def test_list_supervisor_role_forbidden(supervisor_client: AsyncClient) -> None:
    assert (await supervisor_client.get("/api/v1/batches")).status_code == 403


async def test_list_basic_returns_200(warehouse_client: AsyncClient) -> None:
    r = await warehouse_client.get("/api/v1/batches")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_list_pagination_validation(warehouse_client: AsyncClient) -> None:
    assert (await warehouse_client.get("/api/v1/batches?limit=0")).status_code == 422
    assert (await warehouse_client.get("/api/v1/batches?limit=500")).status_code == 422
    assert (await warehouse_client.get("/api/v1/batches?offset=-1")).status_code == 422


async def test_list_status_counts_correct(
    warehouse_client: AsyncClient,
    populated_batch: tuple[Batch, list[Part]],
) -> None:
    batch, _ = populated_batch
    r = await warehouse_client.get("/api/v1/batches?limit=200")
    assert r.status_code == 200
    our = next((it for it in r.json() if it["id"] == str(batch.id)), None)
    assert our is not None
    assert our["total_parts"] == 5
    assert our["pending_count"] == 2
    assert our["active_count"] == 2
    assert our["absorbed_count"] == 1


# === GET /batches/{id} (detail) ===

async def test_detail_no_token_returns_401(client: AsyncClient) -> None:
    assert (await client.get(f"/api/v1/batches/{uuid4()}")).status_code == 401


async def test_detail_supervisor_role_forbidden(supervisor_client: AsyncClient) -> None:
    assert (await supervisor_client.get(f"/api/v1/batches/{uuid4()}")).status_code == 403


async def test_detail_unknown_batch_returns_404(warehouse_client: AsyncClient) -> None:
    assert (await warehouse_client.get(f"/api/v1/batches/{uuid4()}")).status_code == 404


async def test_detail_returns_batch_with_all_parts(
    warehouse_client: AsyncClient,
    populated_batch: tuple[Batch, list[Part]],
) -> None:
    batch, _ = populated_batch
    r = await warehouse_client.get(f"/api/v1/batches/{batch.id}")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == str(batch.id)
    assert len(data["parts"]) == 5
    statuses = sorted(p["status"] for p in data["parts"])
    assert statuses == ["absorbed", "active", "active", "pending", "pending"]


# === POST /batches (create) ===

async def test_create_no_token_returns_401(client: AsyncClient) -> None:
    r = await client.post("/api/v1/batches", json={"part_type": "X", "quantity": 1})
    assert r.status_code == 401


async def test_create_supervisor_role_forbidden(supervisor_client: AsyncClient) -> None:
    r = await supervisor_client.post("/api/v1/batches", json={"part_type": "X", "quantity": 1})
    assert r.status_code == 403


async def test_create_validation_errors(warehouse_client: AsyncClient) -> None:
    """Body вне допустимых границ → 422."""
    cases = [
        {"part_type": "", "quantity": 5},        # part_type пустой
        {"part_type": "D", "quantity": 0},        # quantity < 1
        {"part_type": "D", "quantity": 20000},    # quantity > 10000
        {"part_type": "D"},                       # quantity отсутствует
        {"quantity": 5},                          # part_type отсутствует
    ]
    for body in cases:
        r = await warehouse_client.post("/api/v1/batches", json=body)
        assert r.status_code == 422, f"Должно быть 422 для body={body}, получили {r.status_code}"


async def test_create_happy_path(
    warehouse_client: AsyncClient,
    cleanup_batches: list[UUID],
) -> None:
    """Создание партии: 201, корректная структура ответа, IDs последовательны."""
    unique_type = f"CRT-{uuid7().hex[:6]}"
    r = await warehouse_client.post(
        "/api/v1/batches",
        json={"part_type": unique_type, "quantity": 5},
    )
    assert r.status_code == 201, r.text

    data = r.json()
    cleanup_batches.append(UUID(data["id"]))

    assert data["part_type"] == unique_type
    assert len(data["part_ids"]) == 5
    # Все IDs стартуют с типа и идут по возрастающей
    assert all(pid.startswith(f"{unique_type}-") for pid in data["part_ids"])
    numbers = [int(pid.split("-")[-1]) for pid in data["part_ids"]]
    assert numbers == sorted(numbers)
    # И первая партия для свежего типа стартует с 1
    assert numbers == [1, 2, 3, 4, 5]


async def test_create_numbering_continues(
    warehouse_client: AsyncClient,
    cleanup_batches: list[UUID],
) -> None:
    """Вторая партия того же типа продолжает нумерацию (не пересекается с первой)."""
    unique_type = f"NUM-{uuid7().hex[:6]}"

    r1 = await warehouse_client.post(
        "/api/v1/batches",
        json={"part_type": unique_type, "quantity": 5},
    )
    assert r1.status_code == 201
    data1 = r1.json()
    cleanup_batches.append(UUID(data1["id"]))

    r2 = await warehouse_client.post(
        "/api/v1/batches",
        json={"part_type": unique_type, "quantity": 3},
    )
    assert r2.status_code == 201
    data2 = r2.json()
    cleanup_batches.append(UUID(data2["id"]))

    all_numbers = sorted(
        int(pid.split("-")[-1]) for pid in data1["part_ids"] + data2["part_ids"]
    )
    assert all_numbers == [1, 2, 3, 4, 5, 6, 7, 8]


async def test_create_response_parts_actually_in_db(
    warehouse_client: AsyncClient,
    cleanup_batches: list[UUID],
) -> None:
    """После create детали реально записаны в БД со status=pending."""
    unique_type = f"DB-{uuid7().hex[:6]}"
    r = await warehouse_client.post(
        "/api/v1/batches",
        json={"part_type": unique_type, "quantity": 3},
    )
    assert r.status_code == 201
    data = r.json()
    cleanup_batches.append(UUID(data["id"]))

    # Дёрнем GET /batches/{id} и проверим что детали правда там и pending
    r_detail = await warehouse_client.get(f"/api/v1/batches/{data['id']}")
    assert r_detail.status_code == 200
    detail = r_detail.json()
    assert len(detail["parts"]) == 3
    assert all(p["status"] == "pending" for p in detail["parts"])
