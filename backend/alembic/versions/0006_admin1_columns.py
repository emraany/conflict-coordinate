"""admin1 identity columns on crises

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-05

Adds country_iso3 + admin1 + admin1_norm + intensity_last_week_at to support
the aggregates-as-backbone redesign. The unique constraint on
(country_iso3, admin1_norm) starts as a partial index so existing rows
without admin1 can coexist; the backfill script populates them, and 0008
promotes it to a full unique constraint.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("crises", sa.Column("country_iso3", sa.String(length=3), nullable=True))
    op.add_column("crises", sa.Column("admin1", sa.String(length=120), nullable=True))
    op.add_column("crises", sa.Column("admin1_norm", sa.String(length=120), nullable=True))
    op.add_column(
        "crises",
        sa.Column("intensity_last_week_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_crises_country_iso3", "crises", ["country_iso3"])
    op.create_index(
        "ix_crises_iso3_admin1",
        "crises",
        ["country_iso3", "admin1_norm"],
        unique=True,
        postgresql_where=sa.text("admin1_norm IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_crises_iso3_admin1", table_name="crises")
    op.drop_index("ix_crises_country_iso3", table_name="crises")
    op.drop_column("crises", "intensity_last_week_at")
    op.drop_column("crises", "admin1_norm")
    op.drop_column("crises", "admin1")
    op.drop_column("crises", "country_iso3")
