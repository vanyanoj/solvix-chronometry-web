"""Эндпоинты управления станками (supervisor-блок)."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.auth.dependencies import require_role
from solvix_chronometry.db import get_session
from solvix_chronometry.models.enums import UserRole
from solvix_chronometry.models.hierarchy import Station
from solvix_chronometry.mqtt.publisher import publish_command

router = APIRouter(prefix="/stations", tags=["stations"])


class CommandResponse(BaseModel):
    command_id: str
    station_id: UUID
    command: str
    status: str


@router.post(
    "/{station_id}/restart",
    response_model=CommandResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_role(UserRole.supervisor))],
)
async def restart_station(
    station_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> CommandResponse:
    """Отправить терминалу команду перезагрузки через MQTT.

    Команда асинхронная — 202 означает что публикация удалась,
    но не означает что терминал реально перезагрузился. Терминал получит
    сообщение, корректно завершит текущую операцию (если есть) и перезагрузится.
    """
    station = (await session.execute(
        select(Station).where(Station.id == station_id)
    )).scalar_one_or_none()
    if station is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Station {station_id} not found",
        )

    command_id = await publish_command(station_id, "restart")
    return CommandResponse(
        command_id=command_id,
        station_id=station_id,
        command="restart",
        status="sent",
    )
