"""
Идемпотентный сидер тестовых юзеров.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from solvix_chronometry.auth.hashing import hash_pass_code
from solvix_chronometry.db import SessionLocal as async_session_factory
from solvix_chronometry.models.enums import UserRole
from solvix_chronometry.models.people import User

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger(__name__)


USERS_SPEC: dict[str, tuple[str, UserRole]] = {
    "TEST-002": ("Алексей Иванов", UserRole.supervisor),
    "TEST-WH-001": ("Мария Кладовщикова", UserRole.warehouse),
}


async def upsert_user(
    session: AsyncSession,
    pass_code: str,
    full_name: str,
    role: UserRole,
) -> str:
    result = await session.execute(
        select(User).where(User.pass_code_hash == hash_pass_code(pass_code))
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            pass_code_hash=hash_pass_code(pass_code),
            full_name=full_name,
            role=role,
            active=True,
        )
        session.add(user)
        return f"created  {pass_code:<14} {role.value:<10} {full_name}"

    changes = []
    if user.full_name != full_name:
        user.full_name = full_name
        changes.append("name")
    if user.role != role:
        user.role = role
        changes.append(f"role→{role.value}")
    if not user.active:
        user.active = True
        changes.append("active")

    if changes:
        return f"updated  {pass_code:<14} {role.value:<10} {full_name}  [{', '.join(changes)}]"
    return f"as-is    {pass_code:<14} {role.value:<10} {full_name}"


async def normalize_operators(session: AsyncSession) -> int:
    result = await session.execute(select(User))
    all_users = result.scalars().all()
    spec_hashes = {hash_pass_code(c): c for c in USERS_SPEC}

    changed = 0
    for u in all_users:
        if u.pass_code_hash in spec_hashes:
            continue
        if u.role != UserRole.operator:
            log.info(f"normalize  {u.full_name:<20} {u.role.value} → operator")
            u.role = UserRole.operator
            changed += 1
    return changed


async def seed() -> None:
    async with async_session_factory() as session:
        async with session.begin():
            log.info("Сидим тестовых юзеров:")
            for pass_code, (full_name, role) in USERS_SPEC.items():
                msg = await upsert_user(session, pass_code, full_name, role)
                log.info(msg)

            normalized = await normalize_operators(session)
            if normalized:
                log.info(f"Нормализованы остальные юзера ({normalized} шт.) → role=operator")
            else:
                log.info("Все остальные юзера уже с role=operator")

    log.info("Готово.")


if __name__ == "__main__":
    asyncio.run(seed())
