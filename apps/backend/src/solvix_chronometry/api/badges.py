"""Badges endpoints — управление пулом NFC-бейджей (supervisor-блок).

API-контракт — Обсидиан → Решения №84 (supervisor), №10-11 (NFC как пул).
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.auth.dependencies import require_role
from solvix_chronometry.db import get_session
from solvix_chronometry.models.enums import NfcBadgeStatus, UserRole
from solvix_chronometry.models.people import NfcBadge

router = APIRouter(prefix="/badges", tags=["badges"])


class BadgeResponse(BaseModel):
    id: UUID
    uid: str
    status: NfcBadgeStatus

    model_config = ConfigDict(from_attributes=True)


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
