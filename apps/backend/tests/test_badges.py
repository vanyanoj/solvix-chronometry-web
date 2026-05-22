"""Тесты эндпоинтов badges (supervisor-блок).

Покрытие:
- GET /badges: auth (401/403), 200, фильтр, валидация, структура
- POST /badges: auth (401/403), 422, 201 happy, 409 duplicate
- PATCH /badges/{id}: auth (401/403), 404, 200 status change
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from solvix_chronometry.db import SessionLocal
from solvix_chronometry.models.people import NfcBadge


@pytest_asyncio.fixture
async def test_badge_in_db() -> AsyncIterator[NfcBadge]:
    """Свежесозданный бейдж со статусом по умолчанию (free)."""
    badge_id: UUID | None = None
    try:
        async with SessionLocal() as session:
            b = NfcBadge(uid=f"BADGETEST-{uuid4().hex[:8]}")
            session.add(b)
            await session.commit()
            await session.refresh(b)
            badge_id = b.id
        yield b
    finally:
        if badge_id:
            async with SessionLocal() as session:
                async with session.begin():
                    await session.execute(delete(NfcBadge).where(NfcBadge.id == badge_id))


@pytest_asyncio.fixture
async def cleanup_badges() -> AsyncIterator[list[UUID]]:
    """Cleanup для бейджей созданных через POST API."""
    badge_ids: list[UUID] = []
    yield badge_ids
    if badge_ids:
        async with SessionLocal() as session:
            async with session.begin():
                await session.execute(delete(NfcBadge).where(NfcBadge.id.in_(badge_ids)))


# === GET /badges ===

async def test_list_no_token_returns_401(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/badges")).status_code == 401


async def test_list_warehouse_forbidden(warehouse_client: AsyncClient) -> None:
    assert (await warehouse_client.get("/api/v1/badges")).status_code == 403


async def test_list_returns_200(supervisor_client: AsyncClient) -> None:
    r = await supervisor_client.get("/api/v1/badges")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_list_includes_created_badge(
    supervisor_client: AsyncClient,
    test_badge_in_db: NfcBadge,
) -> None:
    r = await supervisor_client.get("/api/v1/badges?limit=200")
    assert r.status_code == 200
    ids = [it["id"] for it in r.json()]
    assert str(test_badge_in_db.id) in ids


async def test_list_filter_by_free(
    supervisor_client: AsyncClient,
    test_badge_in_db: NfcBadge,
) -> None:
    r = await supervisor_client.get("/api/v1/badges?status=free&limit=200")
    assert r.status_code == 200
    ids = [it["id"] for it in r.json()]
    assert str(test_badge_in_db.id) in ids


async def test_list_invalid_status_returns_422(supervisor_client: AsyncClient) -> None:
    assert (await supervisor_client.get("/api/v1/badges?status=NONSENSE")).status_code == 422


async def test_list_pagination_validation(supervisor_client: AsyncClient) -> None:
    assert (await supervisor_client.get("/api/v1/badges?limit=0")).status_code == 422
    assert (await supervisor_client.get("/api/v1/badges?limit=500")).status_code == 422
    assert (await supervisor_client.get("/api/v1/badges?offset=-1")).status_code == 422


async def test_list_response_structure(
    supervisor_client: AsyncClient,
    test_badge_in_db: NfcBadge,
) -> None:
    r = await supervisor_client.get("/api/v1/badges?limit=200")
    item = next((it for it in r.json() if it["id"] == str(test_badge_in_db.id)), None)
    assert item is not None
    assert set(item.keys()) == {"id", "uid", "status"}


# === POST /badges ===

async def test_create_no_token_returns_401(client: AsyncClient) -> None:
    r = await client.post("/api/v1/badges", json={"uid": "ABC"})
    assert r.status_code == 401


async def test_create_warehouse_forbidden(warehouse_client: AsyncClient) -> None:
    r = await warehouse_client.post("/api/v1/badges", json={"uid": "ABC"})
    assert r.status_code == 403


async def test_create_validation_errors(supervisor_client: AsyncClient) -> None:
    """Пустой uid или слишком длинный → 422."""
    assert (await supervisor_client.post("/api/v1/badges", json={"uid": ""})).status_code == 422
    assert (await supervisor_client.post("/api/v1/badges", json={"uid": "x" * 51})).status_code == 422
    assert (await supervisor_client.post("/api/v1/badges", json={})).status_code == 422


async def test_create_happy_path(
    supervisor_client: AsyncClient,
    cleanup_badges: list[UUID],
) -> None:
    new_uid = f"NEW-BADGE-{uuid4().hex[:8]}"
    r = await supervisor_client.post("/api/v1/badges", json={"uid": new_uid})
    assert r.status_code == 201, r.text

    data = r.json()
    cleanup_badges.append(UUID(data["id"]))
    assert data["uid"] == new_uid
    assert data["status"] == "free"


async def test_create_duplicate_uid_returns_409(
    supervisor_client: AsyncClient,
    test_badge_in_db: NfcBadge,
) -> None:
    """Попытка добавить бейдж с уже существующим UID → 409."""
    r = await supervisor_client.post("/api/v1/badges", json={"uid": test_badge_in_db.uid})
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"].lower()


# === PATCH /badges/{id} ===

async def test_patch_no_token_returns_401(client: AsyncClient) -> None:
    r = await client.patch(f"/api/v1/badges/{uuid4()}", json={"status": "lost"})
    assert r.status_code == 401


async def test_patch_warehouse_forbidden(warehouse_client: AsyncClient) -> None:
    r = await warehouse_client.patch(f"/api/v1/badges/{uuid4()}", json={"status": "lost"})
    assert r.status_code == 403


async def test_patch_unknown_badge_returns_404(supervisor_client: AsyncClient) -> None:
    r = await supervisor_client.patch(f"/api/v1/badges/{uuid4()}", json={"status": "lost"})
    assert r.status_code == 404


async def test_patch_invalid_status_returns_422(
    supervisor_client: AsyncClient,
    test_badge_in_db: NfcBadge,
) -> None:
    r = await supervisor_client.patch(
        f"/api/v1/badges/{test_badge_in_db.id}",
        json={"status": "NONSENSE"},
    )
    assert r.status_code == 422


async def test_patch_mark_as_lost(
    supervisor_client: AsyncClient,
    test_badge_in_db: NfcBadge,
) -> None:
    """Помечаем бейдж как потерянный."""
    r = await supervisor_client.patch(
        f"/api/v1/badges/{test_badge_in_db.id}",
        json={"status": "lost"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["id"] == str(test_badge_in_db.id)
    assert data["status"] == "lost"


async def test_patch_recover_to_free(
    supervisor_client: AsyncClient,
    test_badge_in_db: NfcBadge,
) -> None:
    """Помечаем как lost, потом возвращаем в free (нашли)."""
    r1 = await supervisor_client.patch(
        f"/api/v1/badges/{test_badge_in_db.id}",
        json={"status": "lost"},
    )
    assert r1.status_code == 200

    r2 = await supervisor_client.patch(
        f"/api/v1/badges/{test_badge_in_db.id}",
        json={"status": "free"},
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "free"
