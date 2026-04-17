"""sources.origin column for provenance

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("origin", sa.String(length=40), nullable=True))
    # Backfill: sources tied to fixture crises are tagged 'fixture'; everything else 'curated'.
    op.execute(
        """
        UPDATE sources
        SET origin = CASE
            WHEN crisis_id IN (SELECT id FROM crises WHERE source_name = 'fixture')
                THEN 'fixture'
            ELSE 'curated'
        END
        WHERE origin IS NULL
        """
    )
    op.create_index("ix_sources_origin", "sources", ["origin"])


def downgrade() -> None:
    op.drop_index("ix_sources_origin", table_name="sources")
    op.drop_column("sources", "origin")
