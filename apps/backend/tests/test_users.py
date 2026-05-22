"""Тесты GET /api/v1/users (supervisor-блок).

Особое внимание: pass_code НЕ должен возвращаться (это секрет).
"""

from __future__ import annotations

from httpx import AsyncClient

from solvix_chronometry.models.people import User


async def test_no_token_returns_401(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/users")).status_code == 401


async def test_warehouse_role_forbidden(warehouse_client: AsyncClient) -> None:
    assert (await warehouse_client.get("/api/v1/users")).status_code == 403


async def test_list_returns_200(supervisor_client: AsyncClient) -> None:
    r = await supervisor_client.get("/api/v1/users")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_pass_code_not_in_response(
    supervisor_client: AsyncClient,
    operator_user: User,
) -> None:
    """КРИТИЧНО: pass_code НИКОГДА не уходит во фронт."""
    r = await supervisor_client.get("/api/v1/users?limit=200")
    assert r.status_code == 200
    for item in r.json():
        assert "pass_code" not in item, f"pass_code leaked in response: {item}"


async def test_filter_by_role_operator(
    supervisor_client: AsyncClient,
    operator_user: User,
) -> None:
    """?role=operator показывает оператора, не показывает supervisor/warehouse."""
    r = await supervisor_client.get("/api/v1/users?role=operator&limit=200")
    assert r.status_code == 200
    items = r.json()
    # Наш тестовый оператор в выборке
    ids = [it["id"] for it in items]
    assert str(operator_user.id) in ids
    # Все возвращённые имеют role=operator
    for item in items:
        assert item["role"] == "operator"


async def test_filter_by_role_supervisor(supervisor_client: AsyncClient) -> None:
    """?role=supervisor — возвращает supervisor'ов (в т.ч. логиненный тестовый)."""
    r = await supervisor_client.get("/api/v1/users?role=supervisor&limit=200")
    assert r.status_code == 200
    for item in r.json():
        assert item["role"] == "supervisor"


async def test_invalid_role_returns_422(supervisor_client: AsyncClient) -> None:
    assert (await supervisor_client.get("/api/v1/users?role=NONSENSE")).status_code == 422


async def test_response_structure(
    supervisor_client: AsyncClient,
    operator_user: User,
) -> None:
    """Возвращаются ровно id, full_name, role, active. pass_code и прочее — нет."""
    r = await supervisor_client.get("/api/v1/users?limit=200")
    item = next((it for it in r.json() if it["id"] == str(operator_user.id)), None)
    assert item is not None
    assert set(item.keys()) == {"id", "full_name", "role", "active"}


async def test_pagination_validation(supervisor_client: AsyncClient) -> None:
    assert (await supervisor_client.get("/api/v1/users?limit=0")).status_code == 422
    assert (await supervisor_client.get("/api/v1/users?offset=-1")).status_code == 422
