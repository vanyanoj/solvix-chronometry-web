"""JWT encode/decode для аутентификации пользователей.

PyJWT с HS256 (симметричный — одного секрета достаточно).
Срок жизни — settings.jwt_expires_min минут.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt

from solvix_chronometry.config import settings
from solvix_chronometry.models.enums import UserRole


def create_access_token(user_id: uuid.UUID, role: UserRole) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role.value,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expires_min)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Кидает jwt.ExpiredSignatureError или jwt.InvalidTokenError при проблеме."""
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
