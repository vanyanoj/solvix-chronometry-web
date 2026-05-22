"""Batches endpoints — партии приёмки (warehouse-блок).

API-контракт — Обсидиан → Решения №84 (warehouse) и №30-33 (приёмка).
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.auth.dependencies import require_role
from solvix_chronometry.db import get_session
from solvix_chronometry.models.enums import PartStatus, UserRole
from solvix_chronometry.models.parts import Batch, Part

router = APIRouter(prefix="/batches", tags=["batches"])


# === Response schemas ===

class BatchListItem(BaseModel):
    """Партия в списке: метаданные + счётчики деталей по статусам."""
    id: UUID
    part_type: str
    created_at: datetime
    total_parts: int
    pending_count: int
    active_count: int
    absorbed_count: int


class BatchPartItem(BaseModel):
    """Деталь внутри партии — без избыточных полей batch_id/type."""
    id: str
    base_id: str
    version: int
    status: PartStatus
    parents: list[str]
    station_id: UUID | None = None
    shift_id: UUID | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BatchDetail(BaseModel):
    """Партия + полный список всех деталей внутри."""
    id: UUID
    part_type: str
    created_at: datetime
    parts: list[BatchPartItem]


# === Endpoints ===

@router.get(
    "",
    response_model=list[BatchListItem],
    dependencies=[Depends(require_role(UserRole.warehouse))],
)
async def list_batches(
    limit: int = Query(default=50, ge=1, le=200, description="Сколько вернуть (1-200)"),
    offset: int = Query(default=0, ge=0, description="Смещение для пагинации"),
    session: AsyncSession = Depends(get_session),
) -> list[BatchListItem]:
    """Список партий приёмки с разбивкой по статусам деталей.

    Сортировка: свежие сверху. Пагинация через limit/offset.
    """
    stmt = (
        select(
            Batch.id,
            Batch.part_type,
            Batch.created_at,
            func.count(Part.id).label("total_parts"),
            func.count(Part.id).filter(Part.status == PartStatus.pending).label("pending_count"),
            func.count(Part.id).filter(Part.status == PartStatus.active).label("active_count"),
            func.count(Part.id).filter(Part.status == PartStatus.absorbed).label("absorbed_count"),
        )
        .outerjoin(Part, Part.batch_id == Batch.id)
        .group_by(Batch.id, Batch.part_type, Batch.created_at)
        .order_by(Batch.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).all()

    return [
        BatchListItem(
            id=row.id,
            part_type=row.part_type,
            created_at=row.created_at,
            total_parts=row.total_parts,
            pending_count=row.pending_count,
            active_count=row.active_count,
            absorbed_count=row.absorbed_count,
        )
        for row in rows
    ]


@router.get(
    "/{batch_id}",
    response_model=BatchDetail,
    dependencies=[Depends(require_role(UserRole.warehouse))],
)
async def get_batch(
    batch_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> BatchDetail:
    """Детали партии + полный список её деталей.

    Без пагинации внутри партии — обычно 50-500 деталей, фронту это норм.
    Если в будущем партии станут гигантскими — добавим limit/offset.
    """
    batch = (await session.execute(
        select(Batch).where(Batch.id == batch_id)
    )).scalar_one_or_none()

    if batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch {batch_id} not found",
        )

    parts = (await session.execute(
        select(Part).where(Part.batch_id == batch_id).order_by(Part.id)
    )).scalars().all()

    return BatchDetail(
        id=batch.id,
        part_type=batch.part_type,
        created_at=batch.created_at,
        parts=[BatchPartItem.model_validate(p) for p in parts],
    )
