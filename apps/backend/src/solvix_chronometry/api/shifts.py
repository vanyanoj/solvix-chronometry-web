"""Shifts endpoints — управление сменами операторов (supervisor-блок).

API-контракт — Обсидиан → Решения №84 (supervisor), №10-11 (NFC как пул),
№36-38 (закрытие смены, force_close старшим).
"""
import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.auth.dependencies import require_role
from solvix_chronometry.db import get_session
from solvix_chronometry.models.enums import NfcBadgeStatus, ShiftClosedBy, UserRole
from solvix_chronometry.models.hierarchy import Station
from solvix_chronometry.models.people import NfcBadge, Shift, User
from solvix_chronometry.mqtt.publisher import publish_command

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shifts", tags=["shifts"])


# === Schemas ===

class CreateShiftRequest(BaseModel):
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
    closed_by: ShiftClosedBy | None = None


# === Helpers ===

async def _find_active_shift(
    session: AsyncSession,
    *,
    user_id: UUID | None = None,
    badge_id: UUID | None = None,
    station_id: UUID | None = None,
) -> Shift | None:
    query = select(Shift).where(Shift.unbound_at.is_(None))
    if user_id is not None:
        query = query.where(Shift.user_id == user_id)
    if badge_id is not None:
        query = query.where(Shift.badge_id == badge_id)
    if station_id is not None:
        query = query.where(Shift.station_id == station_id)
    return (await session.execute(query.limit(1))).scalar_one_or_none()


async def _build_shift_response(
    session: AsyncSession, shift: Shift
) -> ShiftResponse:
    """Подгрузить связанные сущности и сформировать ответ."""
    user = (await session.execute(
        select(User).where(User.id == shift.user_id)
    )).scalar_one()
    badge = (await session.execute(
        select(NfcBadge).where(NfcBadge.id == shift.badge_id)
    )).scalar_one()

    if shift.station_id is not None:
        station = (await session.execute(
            select(Station).where(Station.id == shift.station_id)
        )).scalar_one_or_none()
        station_name = station.name if station else "(deleted)"
        station_id = shift.station_id
    else:
        station_name = "(unknown)"
        station_id = shift.station_id  # None

    return ShiftResponse(
        id=shift.id,
        user_id=user.id,
        user_full_name=user.full_name,
        badge_id=badge.id,
        badge_uid=badge.uid,
        station_id=station_id,
        station_name=station_name,
        bound_at=shift.bound_at,
        unbound_at=shift.unbound_at,
        closed_by=shift.closed_by,
    )


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
    """Привязка оператор+бейдж+станок (см. Решение №84)."""
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

    # 2. Валидация user
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

    # 2b. Валидация badge: lost нельзя выдавать, bound уже у кого-то
    if badge.status != NfcBadgeStatus.free:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Badge {badge.uid!r} is already in use or lost (status: {badge.status.value})",
        )

    # 3. Занятость
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

    # 4. Создать (бейдж занимается в той же транзакции)
    shift = Shift(user_id=user.id, badge_id=badge.id, station_id=station.id)
    badge.status = NfcBadgeStatus.bound
    session.add(shift)
    try:
        await session.commit()
    except IntegrityError:
        # Гонка: параллельный запрос успел создать смену между проверками
        # и коммитом. Уникальные partial-индексы в БД — последний рубеж.
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User, station or badge was taken by a concurrent request",
        ) from None
    await session.refresh(shift)

    return await _build_shift_response(session, shift)


@router.post(
    "/{shift_id}/force_close",
    response_model=ShiftResponse,
    dependencies=[Depends(require_role(UserRole.supervisor))],
)
async def force_close_shift(
    shift_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ShiftResponse:
    """Принудительное закрытие смены старшим (Решение №37).

    Используется в исключительных случаях: оператор потерял бейдж, заболел,
    не может вернуться на станок. Устанавливает `unbound_at=now` и
    `closed_by=supervisor` — это попадёт в аудит и аналитику.

    TODO для прода: оптимизировать publisher до persistent-клиента.

    После коммита публикует MQTT-команду `force_close_shift` на терминал
    станка (Решение №80) — ESP32 очищает state. Best-effort: если брокер
    недоступен, смена всё равно закрыта (БД — источник истины), недоставка
    логируется.
    """
    shift = (await session.execute(
        select(Shift).where(Shift.id == shift_id)
    )).scalar_one_or_none()

    if shift is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shift {shift_id} not found",
        )

    if shift.unbound_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Shift is already closed (unbound at {shift.unbound_at.isoformat()})",
        )

    # Закрываем + освобождаем бейдж (если его не пометили lost)
    shift.unbound_at = datetime.now(UTC)
    shift.closed_by = ShiftClosedBy.supervisor
    badge = (await session.execute(
        select(NfcBadge).where(NfcBadge.id == shift.badge_id)
    )).scalar_one_or_none()
    if badge is not None and badge.status == NfcBadgeStatus.bound:
        badge.status = NfcBadgeStatus.free
    await session.commit()
    await session.refresh(shift)

    # Уведомить терминал (best-effort, после коммита)
    try:
        await publish_command(
            shift.station_id,
            "force_close_shift",
            {"shift_id": str(shift.id)},
        )
    except Exception:
        logger.warning(
            "force_close_shift command not delivered to station %s (shift %s)",
            shift.station_id, shift.id, exc_info=True,
        )

    return await _build_shift_response(session, shift)
