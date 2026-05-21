"""add role column to users

Revision ID: 188ce22735db
Revises: 7e2eb9c36560
Create Date: 2026-05-21 20:47:26.566331

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '188ce22735db'
down_revision: str | Sequence[str] | None = '7e2eb9c36560'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    user_role = sa.Enum('warehouse', 'supervisor', 'operator', name='userrole')
    user_role.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'users',
        sa.Column('role', user_role, server_default='operator', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('users', 'role')
    sa.Enum(name='userrole').drop(op.get_bind(), checkfirst=True)
