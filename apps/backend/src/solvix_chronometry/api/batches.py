"""Batches endpoints — партии приёмки (warehouse-блок).

API-контракт — Обсидиан → Решения №84 (warehouse), №30-33 (приёмка), №3-9 (QR/наследование).
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.auth.dependencies import require_role
from solvix_chronometry.db import get_session
from solvix_chronometry.models.enums import PartStatus, UserRole
from solvix_chronometry.models.parts import Batch, Part

router = APIRouter(prefix="/batches", tags=["batches"])


# === Response schemas ===

class BatchListItem(BaseModel):
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
    """Партия + полный список деталей внутри."""
    id: UUID
    part_type: str
    created_at: datetime
    parts: list[BatchPartItem]


class CreateBatchRequest(BaseModel):
    """Тело для создания партии — что и сколько."""
    part_type: str = Field(..., min_length=1, max_length=50, description="Тип детали, напр. 'D'")
    quantity: int = Field(..., ge=1, le=10000, description="Сколько деталей в партии (1-10000)")


class BatchCreatedResponse(BaseModel):
    """Ответ после создания: метаданные партии + IDs всех деталей для печати."""
    id: UUID
    part_type: str
    created_at: datetime
    part_ids: list[str]


# === Helpers ===

async def _next_part_numbers(
    session: AsyncSession, part_type: str, count: int
) -> list[int]:
    """Вернуть N следующих номеров для деталей данного типа.

    Берёт MAX из trailing-digits существующих base_id (напр. из 'D-0050' → 50),
    возвращает [max+1, ..., max+count]. Если деталей этого типа нет — стартует с 1.

    TODO для прода: при одновременных запросах двух кладовщиков — race condition,
    оба получат одинаковый max и попытаются создать одинаковые IDs (UNIQUE conflict).
    Решение — advisory lock на (part_type) или Postgres sequence per type.
    Для пилота с одним кладовщиком — некритично.
    """
    stmt = text(
        r"""
        SELECT COALESCE(MAX(CAST(SUBSTRING(base_id FROM '\d+$') AS INTEGER)), 0)
        FROM parts
        WHERE type = :ptype
        """
    )
    max_num = (await session.execute(stmt, {"ptype": part_type})).scalar() or 0
    return list(range(max_num + 1, max_num + 1 + count))


# === Endpoints ===

@router.get(
    "",
    response_model=list[BatchListItem],
    dependencies=[Depends(require_role(UserRole.warehouse))],
)
async def list_batches(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[BatchListItem]:
    """Список партий с разбивкой деталей по статусам. Свежие сверху."""
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
            id=r.id, part_type=r.part_type, created_at=r.created_at,
            total_parts=r.total_parts,
            pending_count=r.pending_count,
            active_count=r.active_count,
            absorbed_count=r.absorbed_count,
        )
        for r in rows
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
    """Детали партии + полный список её деталей."""
    batch = (await session.execute(
        select(Batch).where(Batch.id == batch_id)
    )).scalar_one_or_none()

    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Batch {batch_id} not found")

    parts = (await session.execute(
        select(Part).where(Part.batch_id == batch_id).order_by(Part.id)
    )).scalars().all()

    return BatchDetail(
        id=batch.id,
        part_type=batch.part_type,
        created_at=batch.created_at,
        parts=[BatchPartItem.model_validate(p) for p in parts],
    )


@router.post(
    "",
    response_model=BatchCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.warehouse))],
)
async def create_batch(
    body: CreateBatchRequest,
    session: AsyncSession = Depends(get_session),
) -> BatchCreatedResponse:
    """Создать партию + N pending-деталей с авто-генерацией ID.

    Решение №30: кладовщик выбирает тип и количество, бэк создаёт batch
    и N parts в статусе pending, возвращает их IDs (фронт отправит на термопринтер).

    Нумерация: следующие номера после max существующего для этого типа.
    Например, если есть D-0001..D-0050 — новая партия из 100 создаст D-0051..D-0150.
    Формат — 4 цифры с ведущими нулями (D-0001). При переполнении (>9999) формат
    расширится естественно (D-10000) — лексическая сортировка пострадает, но
    числовая (cast to int) работает корректно.
    """
    # 1. Узнать следующие номера для этого типа
    numbers = await _next_part_numbers(session, body.part_type, body.quantity)

    # 2. Создать batch (flush для получения batch.id перед созданием parts)
    batch = Batch(part_type=body.part_type)
    session.add(batch)
    await session.flush()

    # 3. Создать parts с авто-генерированными IDs
    part_ids = [f"{body.part_type}-{n:04d}" for n in numbers]
    session.add_all([
        Part(
            id=pid,
            base_id=pid,
            version=0,
            type=body.part_type,
            status=PartStatus.pending,
            parents=[],
            batch_id=batch.id,
        )
        for pid in part_ids
    ])

    await session.commit()
    await session.refresh(batch)

    return BatchCreatedResponse(
        id=batch.id,
        part_type=batch.part_type,
        created_at=batch.created_at,
        part_ids=part_ids,
    )
