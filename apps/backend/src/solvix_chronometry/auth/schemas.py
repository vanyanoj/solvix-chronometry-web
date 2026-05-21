"""Pydantic-схемы для эндпоинтов аутентификации."""

from __future__ import annotations

from pydantic import BaseModel, Field

from solvix_chronometry.models.enums import UserRole


class LoginRequest(BaseModel):
    pass_code: str = Field(min_length=1, description="Код пропуска / UID NFC-бейджа")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Срок жизни токена в секундах")


class CurrentUserResponse(BaseModel):
    id: str
    full_name: str
    role: UserRole
