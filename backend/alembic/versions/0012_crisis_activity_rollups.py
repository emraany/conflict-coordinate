"""crises violence rollups + sources.country_iso3

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-14

`crises.violence_4w_*` / `latest_agg_week` hold the trailing-4-week rollup of
ACLED weekly aggregates restricted to violent event types. They are the
globe's dot layer: computed once per ingest (the live query costs ~1.5s,
far too slow per request).

`sources.country_iso3` scopes ReliefWeb situation reports to a country so
every region dot can surface them, not just named conflicts.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "crises",
        sa.Column(
            "violence_4w_events",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "crises",
        sa.Column(
            "violence_4w_fatalities",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "crises", sa.Column("violence_4w_pop_exposure", sa.Integer(), nullable=True)
    )
    op.add_column("crises", sa.Column("latest_agg_week", sa.Date(), nullable=True))
    op.create_index(
        "ix_crises_violence_4w_events", "crises", ["violence_4w_events"]
    )
    op.add_column(
        "sources", sa.Column("country_iso3", sa.String(length=3), nullable=True)
    )
    op.create_index("ix_sources_country_iso3", "sources", ["country_iso3"])


def downgrade() -> None:
    op.drop_index("ix_sources_country_iso3", table_name="sources")
    op.drop_column("sources", "country_iso3")
    op.drop_index("ix_crises_violence_4w_events", table_name="crises")
    op.drop_column("crises", "latest_agg_week")
    op.drop_column("crises", "violence_4w_pop_exposure")
    op.drop_column("crises", "violence_4w_fatalities")
    op.drop_column("crises", "violence_4w_events")
