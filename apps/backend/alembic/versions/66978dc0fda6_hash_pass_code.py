"""hash pass_code

Revision ID: 66978dc0fda6
Revises: 188ce22735db
Create Date: 2026-07-08 16:23:40.118005

pass_code (plain text) → pass_code_hash (HMAC-SHA256 с pepper).
Бэкфилл: существующие коды хэшируются на месте, данные не теряются.
Downgrade невозможен — хэш необратим.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from solvix_chronometry.auth.hashing import hash_pass_code

# revision identifiers, used by Alembic.
revision: str = '66978dc0fda6'
down_revision: str | Sequence[str] | None = '188ce22735db'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) новая колонка (пока nullable — заполним ниже)
    op.add_column("users", sa.Column("pass_code_hash", sa.String(64), nullable=True))

    # 2) бэкфилл: хэшируем существующие коды
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, pass_code FROM users")).fetchall()
    for user_id, pass_code in rows:
        conn.execute(
            sa.text("UPDATE users SET pass_code_hash = :h WHERE id = :id"),
            {"h": hash_pass_code(pass_code), "id": user_id},
        )

    # 3) ужесточаем и переносим unique
    op.alter_column("users", "pass_code_hash", nullable=False)
    op.create_unique_constraint("uq_users_pass_code_hash", "users", ["pass_code_hash"])

    # 4) прощаемся с plain text
    op.drop_column("users", "pass_code")


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade impossible: pass_code hashes cannot be reversed to plain text."
    )
