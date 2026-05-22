"""Users endpoints — управление пользователями (supervisor-блок).

API-контракт — Обсидиан → Решение №84 (supervisor block).

ВАЖНО: pass_code (используется для логина) НЕ возвращается через API — это секрет.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.auth.dependencies import require_role
from solvix_chronometry.db import get_session
from solvix_chronometry.models.enums import UserRole
from solvix_chronometry.models.people import User

router = APIRouter(prefix="/users", tags=["users"])


class UserResponse(BaseModel):
    """Юзер БЕЗ pass_code (секрет!)."""
    id: UUID
    full_name: str
    role: UserRole
    active: bool

    model_config = ConfigDict(from_attributes=True)


@router.get(
    "",
    response_model=list[UserResponse],
    dependencies=[Depends(require_role(UserRole.supervisor))],
)
async def list_users(
    role: UserRole | None = Query(
        default=None,
        description="Фильтр по роли (warehouse/supervisor/operator). По умолчанию — все.",
    ),
    active: bool | None = Query(
        default=None,
        description="Фильтр по активности. По умолчанию — все (и активные, и нет).",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[User]:
    """Список пользователей. Для распределителя — `?role=operator&active=true`."""
    query = select(User)
    if role is not None:
        query = query.where(User.role == role)
    if active is not None:
        query = query.where(User.active == active)
    query = query.order_by(User.full_name).limit(limit).offset(offset)
    users = (await session.execute(query)).scalars().all()
    return users
