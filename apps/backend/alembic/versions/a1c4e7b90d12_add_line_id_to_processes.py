"""add line_id to processes

Решение №85: изделие / сборочный поток = линия. Бэкфилл: у существующих
строк линия берётся со станка (stations.line_id).

Revision ID: a1c4e7b90d12
Revises: 4f33f8a7c2fd
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a1c4e7b90d12"
down_revision = "4f33f8a7c2fd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "processes",
        sa.Column("line_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_processes_line_id", "processes", "lines",
        ["line_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_processes_line_id", "processes", ["line_id"])
    op.execute(
        """
        UPDATE processes p
        SET line_id = s.line_id
        FROM stations s
        WHERE p.station_hint = s.id
          AND p.line_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_processes_line_id", table_name="processes")
    op.drop_constraint("fk_processes_line_id", "processes", type_="foreignkey")
    op.drop_column("processes", "line_id")
