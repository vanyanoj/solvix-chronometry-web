"""Эндпоинты аутентификации."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.auth.dependencies import get_current_user
from solvix_chronometry.auth.hashing import hash_pass_code
from solvix_chronometry.auth.jwt import create_access_token
from solvix_chronometry.auth.schemas import CurrentUserResponse, LoginRequest, TokenResponse
from solvix_chronometry.config import settings
from solvix_chronometry.db import get_session
from solvix_chronometry.models.enums import UserRole
from solvix_chronometry.models.people import User

router = APIRouter(prefix="/auth", tags=["auth"])

# Роли которым разрешён веб-логин. Operator — нет, у него NFC на терминале.
WEB_LOGIN_ROLES = {UserRole.supervisor, UserRole.warehouse}


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Логин по pass_code → JWT для supervisor/warehouse."""

    result = await session.execute(
        select(User).where(
            User.pass_code_hash == hash_pass_code(payload.pass_code),
            User.active.is_(True),
        )
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid pass_code",
        )

    if user.role not in WEB_LOGIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Role '{user.role.value}' is not allowed to login via web. "
                "Operators authenticate via NFC at the terminal."
            ),
        )

    token = create_access_token(user.id, user.role)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.jwt_expires_min * 60,
    )


@router.get("/me", response_model=CurrentUserResponse)
async def me(user: User = Depends(get_current_user)) -> CurrentUserResponse:
    """Кто я — для проверки токена и подгрузки профиля на фронте."""
    return CurrentUserResponse(
        id=str(user.id),
        full_name=user.full_name,
        role=user.role,
    )
