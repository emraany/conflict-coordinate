"""admin_curated flag on crisis_actors

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-03

Protects admin-added actor links from being wiped when an ingestion source
re-materializes its crises (e.g. ACLED's wholesale re-cluster on every run).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "crisis_actors",
        sa.Column(
            "admin_curated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("crisis_actors", "admin_curated")
