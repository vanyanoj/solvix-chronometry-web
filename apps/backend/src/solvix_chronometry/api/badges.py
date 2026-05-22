"""Badges endpoints — управление пулом NFC-бейджей (supervisor-блок).

API-контракт — Обсидиан → Решения №84 (supervisor), №10-11 (NFC как пул).
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.auth.dependencies import require_role
from solvix_chronometry.db import get_session
from solvix_chronometry.models.enums import NfcBadgeStatus, UserRole
from solvix_chronometry.models.people import NfcBadge

router = APIRouter(prefix="/badges", tags=["badges"])


# === Schemas ===

class BadgeResponse(BaseModel):
    id: UUID
    uid: str
    status: NfcBadgeStatus

    model_config = ConfigDict(from_attributes=True)


class CreateBadgeRequest(BaseModel):
    """Тело при добавлении нового бейджа в пул. UID — это UID физической карты."""
    uid: str = Field(..., min_length=1, max_length=50, description="UID физической NFC-карты")


class UpdateBadgeRequest(BaseModel):
    """Тело при обновлении бейджа. На пилоте — только смена статуса."""
    status: NfcBadgeStatus


# === Endpoints ===

@router.get(
    "",
    response_model=list[BadgeResponse],
    dependencies=[Depends(require_role(UserRole.supervisor))],
)
async def list_badges(
    status: NfcBadgeStatus | None = Query(
        default=None,
        description="Фильтр по статусу (free / in_use / lost). По умолчанию — все.",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[NfcBadge]:
    """Список NFC-бейджей. Для распределителя — фильтр `?status=free` показывает доступные."""
    query = select(NfcBadge)
    if status is not None:
        query = query.where(NfcBadge.status == status)
    query = query.order_by(NfcBadge.uid).limit(limit).offset(offset)
    badges = (await session.execute(query)).scalars().all()
    return badges


@router.post(
    "",
    response_model=BadgeResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.supervisor))],
)
async def create_badge(
    body: CreateBadgeRequest,
    session: AsyncSession = Depends(get_session),
) -> NfcBadge:
    """Добавить новый бейдж в пул. UID берётся со скана физической карты.

    Уникальность: 409 если бейдж с таким UID уже есть.
    Статус по умолчанию — free (бейдж готов к выдаче оператору).
    """
    existing = (await session.execute(
        select(NfcBadge).where(NfcBadge.uid == body.uid)
    )).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Badge with uid {body.uid!r} already exists",
        )

    badge = NfcBadge(uid=body.uid)  # status defaults to free
    session.add(badge)
    await session.commit()
    await session.refresh(badge)
    return badge


@router.patch(
    "/{badge_id}",
    response_model=BadgeResponse,
    dependencies=[Depends(require_role(UserRole.supervisor))],
)
async def update_badge(
    badge_id: UUID,
    body: UpdateBadgeRequest,
    session: AsyncSession = Depends(get_session),
) -> NfcBadge:
    """Обновить статус бейджа.

    Основной кейс на пилоте — пометить бейдж как `lost` (когда оператор потерял).
    Также можно вернуть в `free` если бейдж нашли.
    """
    badge = (await session.execute(
        select(NfcBadge).where(NfcBadge.id == badge_id)
    )).scalar_one_or_none()

    if badge is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Badge {badge_id} not found",
        )

    badge.status = body.status
    await session.commit()
    await session.refresh(badge)
    return badge
