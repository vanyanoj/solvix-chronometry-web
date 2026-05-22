"""Parts endpoints — детали (warehouse-блок).

API-контракт — Обсидиан → Решения №84 (warehouse block) и №3-9 (QR/наследование).
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
    """Получить деталь по ID.

    ID — строковый композит вида `D-0001` или `D-0001.2`.
    Возвращает 404 если деталь не найдена.
    """
    part = (await session.execute(
        select(Part).where(Part.id == part_id)
    )).scalar_one_or_none()

    if part is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Part {part_id!r} not found",
        )

    return part
