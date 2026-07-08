"""
Shared pytest fixtures для интеграционных тестов.

Подход: создаём тестовых юзеров с уникальным pass_code в реальную dev-БД,
после теста удаляем по id. Никакой транзакционной магии — эндпоинты
используют свою сессию через FastAPI DI, нам нужно чтобы данные были видны.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from solvix_chronometry.auth.hashing import hash_pass_code
from solvix_chronometry.auth.jwt import create_access_token
from solvix_chronometry.db import SessionLocal
from solvix_chronometry.main import app
from solvix_chronometry.models.enums import UserRole
from solvix_chronometry.models.people import User
from solvix_chronometry.uuid_v7 import uuid7


# ---------------------------------------------------------------------------
# Создание тестовых юзеров (с auto-cleanup)
# ---------------------------------------------------------------------------

async def _make_user(role: UserRole, prefix: str) -> User:
    """Создаёт юзера с уникальным pass_code, возвращает detached-объект."""
    pass_code = f"{prefix}-{uuid7().hex[:8]}"  # plain-код, в БД уходит хэш
    async with SessionLocal() as session:
        user = User(
            pass_code_hash=hash_pass_code(pass_code),
            full_name=f"Test {role.value.capitalize()}",
            role=role,
            active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def _delete_user(user_id) -> None:
    async with SessionLocal() as session:
        async with session.begin():
            await session.execute(delete(User).where(User.id == user_id))


@pytest_asyncio.fixture
async def supervisor_user() -> AsyncIterator[User]:
    user = await _make_user(UserRole.supervisor, "FIXT-SUP")
    try:
        yield user
    finally:
        await _delete_user(user.id)


@pytest_asyncio.fixture
async def warehouse_user() -> AsyncIterator[User]:
    user = await _make_user(UserRole.warehouse, "FIXT-WH")
    try:
        yield user
    finally:
        await _delete_user(user.id)


@pytest_asyncio.fixture
async def operator_user() -> AsyncIterator[User]:
    user = await _make_user(UserRole.operator, "FIXT-OP")
    try:
        yield user
    finally:
        await _delete_user(user.id)


# ---------------------------------------------------------------------------
# JWT-токены
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def supervisor_token(supervisor_user: User) -> str:
    return create_access_token(user_id=supervisor_user.id, role=supervisor_user.role)


@pytest_asyncio.fixture
async def warehouse_token(warehouse_user: User) -> str:
    return create_access_token(user_id=warehouse_user.id, role=warehouse_user.role)


@pytest_asyncio.fixture
async def operator_token(operator_user: User) -> str:
    return create_access_token(user_id=operator_user.id, role=operator_user.role)


# ---------------------------------------------------------------------------
# HTTP-клиенты
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Клиент без auth — для login и публичных эндпоинтов."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def supervisor_client(supervisor_token: str) -> AsyncIterator[AsyncClient]:
    """Клиент с JWT supervisor'а в Authorization."""
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {supervisor_token}"}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as ac:
        yield ac


@pytest_asyncio.fixture
async def warehouse_client(warehouse_token: str) -> AsyncIterator[AsyncClient]:
    """Клиент с JWT warehouse'а в Authorization."""
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {warehouse_token}"}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as ac:
        yield ac
