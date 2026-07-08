"""shift race indexes + badge status

Revision ID: 4f33f8a7c2fd
Revises: 66978dc0fda6

1) Partial unique индексы на shifts (WHERE unbound_at IS NULL):
   гарантия «одна активная смена на юзера/станок/бейдж» на уровне БД —
   закрывает гонку между проверками и INSERT в create_shift.
2) Backfill nfc_badges.status: бейджи с активной сменой → bound.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '4f33f8a7c2fd'
down_revision: str | Sequence[str] | None = '66978dc0fda6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for col in ("user_id", "station_id", "badge_id"):
        op.create_index(
            f"uq_shifts_active_{col}",
            "shifts",
            [col],
            unique=True,
            postgresql_where=sa.text("unbound_at IS NULL"),
        )

    op.execute(
        """
        UPDATE nfc_badges SET status = 'bound'
        WHERE status = 'free' AND id IN (
            SELECT badge_id FROM shifts WHERE unbound_at IS NULL
        )
        """
    )


def downgrade() -> None:
    for col in ("user_id", "station_id", "badge_id"):
        op.drop_index(f"uq_shifts_active_{col}", table_name="shifts")
    # backfill статусов не откатываем — состояние bound корректно в любом случае
