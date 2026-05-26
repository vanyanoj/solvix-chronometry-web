"""Тесты эндпоинтов управления станками (supervisor-блок)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from solvix_chronometry.db import SessionLocal
from solvix_chronometry.models.hierarchy import Line, Station


@pytest_asyncio.fixture
async def temp_station() -> AsyncIterator[Station]:
    sid: UUID | None = None
    try:
        async with SessionLocal() as session:
            line = (await session.execute(select(Line).limit(1))).scalar_one_or_none()
            if line is None:
                raise RuntimeError("Нет Line в БД.")
            unique = uuid4().hex[:8]
            st = Station(
                line_id=line.id,
                name=f"RestartTest-{unique[:6]}",
                terminal_mac=f"02:{unique[0:2]}:{unique[2:4]}:{unique[4:6]}:11:11",
            )
            session.add(st)
            await session.commit()
            await session.refresh(st)
            sid = st.id
        async with SessionLocal() as session:
            yield (await session.execute(select(Station).where(Station.id == sid))).scalar_one()
    finally:
        if sid:
            async with SessionLocal() as session:
                async with session.begin():
                    await session.execute(delete(Station).where(Station.id == sid))


async def test_restart_no_token_returns_401(client: AsyncClient) -> None:
    assert (await client.post(f"/api/v1/stations/{uuid4()}/restart")).status_code == 401


async def test_restart_warehouse_forbidden(warehouse_client: AsyncClient) -> None:
    assert (await warehouse_client.post(f"/api/v1/stations/{uuid4()}/restart")).status_code == 403


async def test_restart_unknown_station_returns_404(supervisor_client: AsyncClient) -> None:
    r = await supervisor_client.post(f"/api/v1/stations/{uuid4()}/restart")
    assert r.status_code == 404


async def test_restart_existing_station_returns_202(
    supervisor_client: AsyncClient, temp_station: Station,
) -> None:
    """С моком publish_command endpoint возвращает 202 + валидный command_id."""
    mock_publish = AsyncMock(return_value="mock-cmd-uuid")
    with patch("solvix_chronometry.api.stations.publish_command", new=mock_publish):
        r = await supervisor_client.post(f"/api/v1/stations/{temp_station.id}/restart")

    assert r.status_code == 202
    data = r.json()
    assert data["station_id"] == str(temp_station.id)
    assert data["command"] == "restart"
    assert data["command_id"] == "mock-cmd-uuid"
    assert data["status"] == "sent"

    # Проверяем что publish_command был вызван с правильными аргументами
    mock_publish.assert_called_once_with(temp_station.id, "restart")
