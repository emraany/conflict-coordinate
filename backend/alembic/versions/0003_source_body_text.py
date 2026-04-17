"""sources.body_text + new source_type values (situation_report, reference)

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enum additions must run outside a transaction on older Postgres; on 16+
    # ADD VALUE IF NOT EXISTS works mid-transaction. We use COMMIT to be safe.
    op.execute("COMMIT")
    op.execute("ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'situation_report'")
    op.execute("ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'reference'")

    op.add_column("sources", sa.Column("body_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("sources", "body_text")
    # Enum values cannot be removed in Postgres without recreating the type;
    # leave the two new values in place on downgrade.
