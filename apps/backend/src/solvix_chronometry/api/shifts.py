"""Shifts endpoints — управление сменами операторов (supervisor-блок).

API-контракт — Обсидиан → Решения №84 (supervisor), №10-11 (NFC как пул),
№36-38 (закрытие смены).
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.auth.dependencies import require_role
from solvix_chronometry.db import get_session
from solvix_chronometry.models.enums import UserRole
from solvix_chronometry.models.hierarchy import Station
from solvix_chronometry.models.people import NfcBadge, Shift, User

router = APIRouter(prefix="/shifts", tags=["shifts"])


# === Schemas ===

class CreateShiftRequest(BaseModel):
    """Тело для привязки: оператор + бейдж + станок (всё по UUID)."""
    user_id: UUID
    badge_id: UUID
    station_id: UUID


class ShiftResponse(BaseModel):
    """Смена + человекочитаемые имена для фронта."""
    id: UUID
    user_id: UUID
    user_full_name: str
    badge_id: UUID
    badge_uid: str
    station_id: UUID
    station_name: str
    bound_at: datetime
    unbound_at: datetime | None = None


# === Helpers ===

async def _find_active_shift(
    session: AsyncSession,
    *,
    user_id: UUID | None = None,
    badge_id: UUID | None = None,
    station_id: UUID | None = None,
) -> Shift | None:
    """Найти существующую активную смену по одному из id (или None)."""
    query = select(Shift).where(Shift.unbound_at.is_(None))
    if user_id is not None:
        query = query.where(Shift.user_id == user_id)
    if badge_id is not None:
        query = query.where(Shift.badge_id == badge_id)
    if station_id is not None:
        query = query.where(Shift.station_id == station_id)
    return (await session.execute(query.limit(1))).scalar_one_or_none()


# === Endpoints ===

@router.post(
    "",
    response_model=ShiftResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.supervisor))],
)
async def create_shift(
    body: CreateShiftRequest,
    session: AsyncSession = Depends(get_session),
) -> ShiftResponse:
    """Привязка оператор+бейдж+станок — старший приложил бейдж оператора на свой ридер.

    Бизнес-правила:
    - user/badge/station должны существовать → иначе 404 с указанием чего нет
    - user.role == operator и user.active → иначе 409
    - У оператора нет другой активной смены → иначе 409
    - Станок не занят другой сменой → иначе 409
    - Бейдж не используется в другой смене → иначе 409

    Проверки «занятости» — через активные shifts (unbound_at IS NULL),
    единая истина в одном месте.
    """
    # 1. Существование
    user = (await session.execute(
        select(User).where(User.id == body.user_id)
    )).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"User {body.user_id} not found")

    badge = (await session.execute(
        select(NfcBadge).where(NfcBadge.id == body.badge_id)
    )).scalar_one_or_none()
    if badge is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Badge {body.badge_id} not found")

    station = (await session.execute(
        select(Station).where(Station.id == body.station_id)
    )).scalar_one_or_none()
    if station is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Station {body.station_id} not found")

    # 2. Валидация полей user
    if user.role != UserRole.operator:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User has role '{user.role.value}', only 'operator' can have a shift",
        )
    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User {user.full_name!r} is inactive",
        )

    # 3. Проверки занятости (через активные shifts)
    if await _find_active_shift(session, user_id=user.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User {user.full_name!r} already has an active shift",
        )
    if await _find_active_shift(session, station_id=station.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Station {station.name!r} is already occupied",
        )
    if await _find_active_shift(session, badge_id=badge.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Badge {badge.uid!r} is already in use",
        )

    # 4. Создать смену
    shift = Shift(
        user_id=user.id,
        badge_id=badge.id,
        station_id=station.id,
    )
    session.add(shift)
    await session.commit()
    await session.refresh(shift)

    return ShiftResponse(
        id=shift.id,
        user_id=user.id,
        user_full_name=user.full_name,
        badge_id=badge.id,
        badge_uid=badge.uid,
        station_id=station.id,
        station_name=station.name,
        bound_at=shift.bound_at,
        unbound_at=shift.unbound_at,
    )
