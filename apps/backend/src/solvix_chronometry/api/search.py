"""Поиск по сотрудникам и деталям (supervisor-блок).

См. Обсидиан → Решение №84 (структура API).
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.auth.dependencies import require_role
from solvix_chronometry.db import get_session
from solvix_chronometry.models.enums import PartStatus, UserRole
from solvix_chronometry.models.parts import Part
from solvix_chronometry.models.people import User

router = APIRouter(prefix="/search", tags=["search"])


# === Schemas ===

class UserSearchItem(BaseModel):
    id: UUID
    full_name: str
    role: UserRole
    active: bool

    model_config = ConfigDict(from_attributes=True)


class PartSearchItem(BaseModel):
    id: str
    base_id: str
    version: int
    type: str
    status: PartStatus

    model_config = ConfigDict(from_attributes=True)


# === Endpoints ===

@router.get(
    "/users",
    response_model=list[UserSearchItem],
    dependencies=[Depends(require_role(UserRole.supervisor))],
)
async def search_users(
    q: str | None = Query(default=None, description="Подстрока для поиска по ФИО (case-insensitive)"),
    role: UserRole | None = Query(default=None),
    active: bool | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[User]:
    """Поиск сотрудников по ФИО с опциональными фильтрами."""
    query = select(User)
    if q:
        query = query.where(User.full_name.ilike(f"%{q}%"))
    if role is not None:
        query = query.where(User.role == role)
    if active is not None:
        query = query.where(User.active == active)
    query = query.order_by(User.full_name).limit(limit).offset(offset)
    return (await session.execute(query)).scalars().all()


@router.get(
    "/parts",
    response_model=list[PartSearchItem],
    dependencies=[Depends(require_role(UserRole.supervisor))],
)
async def search_parts(
    q: str | None = Query(default=None, description="Подстрока для поиска по id детали (case-insensitive)"),
    status: PartStatus | None = Query(default=None),
    type: str | None = Query(default=None, description="Фильтр по типу детали"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[Part]:
    """Поиск деталей по id с опциональными фильтрами."""
    query = select(Part)
    if q:
        query = query.where(Part.id.ilike(f"%{q}%"))
    if status is not None:
        query = query.where(Part.status == status)
    if type is not None:
        query = query.where(Part.type == type)
    query = query.order_by(Part.id).limit(limit).offset(offset)
    return (await session.execute(query)).scalars().all()
