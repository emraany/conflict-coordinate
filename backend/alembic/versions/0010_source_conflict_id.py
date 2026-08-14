"""sources.conflict_id — conflict-scoped sources (ReliefWeb situation reports)

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-13

A source row belongs to either a crisis (event-derived citations) or a
conflict (dossier-level material like ReliefWeb situation reports).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column(
            "conflict_id",
            sa.Integer(),
            sa.ForeignKey("conflicts.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_sources_conflict_id", "sources", ["conflict_id"])


def downgrade() -> None:
    op.drop_index("ix_sources_conflict_id", table_name="sources")
    op.drop_column("sources", "conflict_id")
