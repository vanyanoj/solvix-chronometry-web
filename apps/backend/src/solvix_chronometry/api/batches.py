"""Batches endpoints — партии приёмки (warehouse-блок).

API-контракт — Обсидиан → Решения №84 (warehouse) и №30-33 (приёмка).
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.auth.dependencies import require_role
from solvix_chronometry.db import get_session
from solvix_chronometry.models.enums import PartStatus, UserRole
from solvix_chronometry.models.parts import Batch, Part

router = APIRouter(prefix="/batches", tags=["batches"])


# === Response schemas ===

class BatchListItem(BaseModel):
    """Партия в списке: метаданные + счётчики деталей по статусам.

    Из этих счётчиков фронт сразу видит:
    - pending_count > 0  → приёмка ещё идёт (есть напечатанные но не сканированные QR)
    - active_count       → сколько деталей сейчас на складе из этой партии
    - absorbed_count     → сколько уже ушло в сборку
    """
    id: UUID
    part_type: str
    created_at: datetime
    total_parts: int
    pending_count: int
    active_count: int
    absorbed_count: int


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

    Сортировка: свежие сверху (`created_at DESC`).
    Пагинация: `?limit=50&offset=0` (по умолчанию первая страница из 50).
    Один SQL-запрос с LEFT JOIN parts и GROUP BY — без N+1.
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
