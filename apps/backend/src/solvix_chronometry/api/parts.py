"""Parts endpoints — детали (warehouse-блок).

API-контракт — Обсидиан → Решения №84 (warehouse) и №3-9 (QR/наследование), №30-31 (приёмка).
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.auth.dependencies import require_role
from solvix_chronometry.db import get_session
from solvix_chronometry.models.enums import PartStatus, UserRole
from solvix_chronometry.models.parts import Part

router = APIRouter(prefix="/parts", tags=["parts"])


# === Response schemas ===

class PartResponse(BaseModel):
    """Полные данные детали."""
    id: str
    base_id: str
    version: int
    type: str
    status: PartStatus
    parents: list[str]
    batch_id: UUID
    station_id: UUID | None = None
    shift_id: UUID | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# === Endpoints ===

@router.get(
    "/{part_id}",
    response_model=PartResponse,
    dependencies=[Depends(require_role(UserRole.warehouse))],
)
async def get_part(
    part_id: str,
    session: AsyncSession = Depends(get_session),
) -> Part:
    """Получить деталь по ID. ID — строковый композит (`D-0001` или `D-0001.2`)."""
    part = (await session.execute(
        select(Part).where(Part.id == part_id)
    )).scalar_one_or_none()

    if part is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Part {part_id!r} not found",
        )

    return part


@router.post(
    "/{part_id}/confirm",
    response_model=PartResponse,
    dependencies=[Depends(require_role(UserRole.warehouse))],
)
async def confirm_part(
    part_id: str,
    session: AsyncSession = Depends(get_session),
) -> Part:
    """Подтвердить деталь (pending → active) — кладовщик отсканировал QR.

    Решение №30, шаг 5: «Сканирует каждый QR по одному → каждая деталь получает
    статус `active`». Это самый горячий эндпоинт кладовщика — нажимается на каждой
    физической детали при приёмке.

    Ответы:
    - 200: деталь была pending, переведена в active
    - 404: деталь не найдена в БД
    - 409: деталь уже active (повторный скан — UX-сигнал кладовщику)
           или absorbed (использована в сборке, подтвердить нельзя)
    """
    part = (await session.execute(
        select(Part).where(Part.id == part_id)
    )).scalar_one_or_none()

    if part is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Part {part_id!r} not found",
        )

    if part.status == PartStatus.active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Part {part_id!r} is already active",
        )

    if part.status == PartStatus.absorbed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Part {part_id!r} is absorbed (used in assembly) and cannot be confirmed",
        )

    # status == pending → переводим в active
    part.status = PartStatus.active
    await session.commit()
    await session.refresh(part)

    return part
