"""Хэширование pass_code.

Почему HMAC-SHA256 с pepper, а не argon2/bcrypt:
логин идёт по одному коду без юзернейма, поэтому нужен детерминированный
хэш для поиска по unique-индексу. Pepper хранится в .env (не в БД) —
дамп базы без него бесполезен для восстановления кодов.
"""

from __future__ import annotations

import hashlib
import hmac

from solvix_chronometry.config import settings


def hash_pass_code(pass_code: str) -> str:
    """Детерминированный HMAC-SHA256 хэш кода (hex, 64 символа)."""
    return hmac.new(
        settings.pass_code_pepper.encode("utf-8"),
        pass_code.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
