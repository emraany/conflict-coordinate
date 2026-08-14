"""conflicts.coord_source — which tier produced the dot coordinate

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-07

Values: event_centroid | footprint_centroid | curated_coordinate |
country_fallback. Written by the routing backfill (and the seed script for
curated coordinates). `country_fallback` marks an approximate display-only
position — the API/frontend must not render it as a confident conflict
location, and such conflicts may not be `active`.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conflicts", sa.Column("coord_source", sa.String(length=20), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("conflicts", "coord_source")
