"""Sanity-тест: фикстуры conftest + auth-эндпоинт /me работают вместе.

Цель — не покрыть весь auth (это уже сделано curl-ом), а УБЕДИТЬСЯ что
автотест-инфра живая: фикстуры создают юзера, токен валиден, клиент с
заголовком ходит до защищённого эндпоинта и получает корректный ответ.
"""

from __future__ import annotations

from httpx import AsyncClient

from solvix_chronometry.models.people import User


async def test_no_token_returns_401(client: AsyncClient) -> None:
    """Без Authorization-заголовка /auth/me отдаёт 401."""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_supervisor_can_get_me(
    supervisor_client: AsyncClient,
    supervisor_user: User,
) -> None:
    """С supervisor-токеном /auth/me возвращает данные юзера."""
    response = await supervisor_client.get("/api/v1/auth/me")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["id"] == str(supervisor_user.id)
    assert data["full_name"] == supervisor_user.full_name
    assert data["role"] == "supervisor"


async def test_warehouse_token_also_works(
    warehouse_client: AsyncClient,
    warehouse_user: User,
) -> None:
    """То же самое, но с warehouse-ролью."""
    response = await warehouse_client.get("/api/v1/auth/me")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["id"] == str(warehouse_user.id)
    assert data["role"] == "warehouse"
