"""Тесты GET /api/v1/badges (supervisor-блок)."""

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


async def test_no_token_returns_401(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/badges")).status_code == 401


async def test_warehouse_role_forbidden(warehouse_client: AsyncClient) -> None:
    assert (await warehouse_client.get("/api/v1/badges")).status_code == 403


async def test_list_returns_200(supervisor_client: AsyncClient) -> None:
    r = await supervisor_client.get("/api/v1/badges")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_created_badge_appears_in_list(
    supervisor_client: AsyncClient,
    test_badge_in_db: NfcBadge,
) -> None:
    """Созданный бейдж попадает в общий список."""
    r = await supervisor_client.get("/api/v1/badges?limit=200")
    assert r.status_code == 200
    ids = [it["id"] for it in r.json()]
    assert str(test_badge_in_db.id) in ids


async def test_filter_by_free_includes_new_badge(
    supervisor_client: AsyncClient,
    test_badge_in_db: NfcBadge,
) -> None:
    """Новый бейдж по умолчанию free — попадает в ?status=free."""
    r = await supervisor_client.get("/api/v1/badges?status=free&limit=200")
    assert r.status_code == 200
    ids = [it["id"] for it in r.json()]
    assert str(test_badge_in_db.id) in ids


async def test_invalid_status_returns_422(supervisor_client: AsyncClient) -> None:
    """Несуществующее значение enum → 422 от валидации."""
    r = await supervisor_client.get("/api/v1/badges?status=NONSENSE")
    assert r.status_code == 422


async def test_pagination_validation(supervisor_client: AsyncClient) -> None:
    assert (await supervisor_client.get("/api/v1/badges?limit=0")).status_code == 422
    assert (await supervisor_client.get("/api/v1/badges?limit=500")).status_code == 422
    assert (await supervisor_client.get("/api/v1/badges?offset=-1")).status_code == 422


async def test_response_structure(
    supervisor_client: AsyncClient,
    test_badge_in_db: NfcBadge,
) -> None:
    """В ответе ровно ожидаемые поля, ничего лишнего."""
    r = await supervisor_client.get("/api/v1/badges?limit=200")
    item = next((it for it in r.json() if it["id"] == str(test_badge_in_db.id)), None)
    assert item is not None
    assert set(item.keys()) == {"id", "uid", "status"}
