"""crisis_intensity_weekly + admin1_aliases + admin1_polygons + crisis_slug_aliases

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-05

* `crisis_intensity_weekly` stores ACLED weekly aggregates per crisis × week ×
  event_type — the real-time signal driving status and the 52-week sparkline.
* `admin1_aliases` maps spelling variants (UCDP, Natural Earth, etc.) to ACLED
  canonical admin1 names so events from multiple sources can find their dot.
* `admin1_polygons` holds Natural Earth admin1 geometries for GDELT
  point-in-polygon attach.
* `crisis_slug_aliases` lets old DBSCAN-cluster-based slugs 301 to the new
  admin1-keyed slugs while bookmarks age out.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crisis_intensity_weekly",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "crisis_id",
            sa.Integer(),
            sa.ForeignKey("crises.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fatalities", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("population_exposure", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_intensity_crisis_week",
        "crisis_intensity_weekly",
        ["crisis_id", "week_start"],
    )
    op.create_index(
        "ix_intensity_crisis_week_type",
        "crisis_intensity_weekly",
        ["crisis_id", "week_start", "event_type"],
        unique=True,
    )

    op.create_table(
        "admin1_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("country_iso3", sa.String(length=3), nullable=False),
        sa.Column("alias_norm", sa.String(length=120), nullable=False),
        sa.Column("canonical_admin1_norm", sa.String(length=120), nullable=False),
        sa.Column("canonical_admin1", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_admin1_aliases_country_alias",
        "admin1_aliases",
        ["country_iso3", "alias_norm"],
        unique=True,
    )
    op.create_index(
        "ix_admin1_aliases_country_canonical",
        "admin1_aliases",
        ["country_iso3", "canonical_admin1_norm"],
    )

    op.create_table(
        "admin1_polygons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("country_iso3", sa.String(length=3), nullable=False),
        sa.Column("admin1", sa.String(length=120), nullable=False),
        sa.Column("admin1_norm", sa.String(length=120), nullable=False),
        sa.Column("centroid_lat", sa.Float(), nullable=True),
        sa.Column("centroid_lng", sa.Float(), nullable=True),
        sa.Column(
            "geom",
            Geometry(geometry_type="MULTIPOLYGON", srid=4326),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_admin1_polygons_country_admin1",
        "admin1_polygons",
        ["country_iso3", "admin1_norm"],
        unique=True,
    )
    op.execute(
        "CREATE INDEX ix_admin1_polygons_geom ON admin1_polygons USING GIST (geom)"
    )

    op.create_table(
        "crisis_slug_aliases",
        sa.Column("old_slug", sa.String(length=120), primary_key=True),
        sa.Column(
            "crisis_id",
            sa.Integer(),
            sa.ForeignKey("crises.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_crisis_slug_aliases_crisis_id",
        "crisis_slug_aliases",
        ["crisis_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_crisis_slug_aliases_crisis_id", table_name="crisis_slug_aliases")
    op.drop_table("crisis_slug_aliases")
    op.execute("DROP INDEX IF EXISTS ix_admin1_polygons_geom")
    op.drop_index("ix_admin1_polygons_country_admin1", table_name="admin1_polygons")
    op.drop_table("admin1_polygons")
    op.drop_index("ix_admin1_aliases_country_canonical", table_name="admin1_aliases")
    op.drop_index("ix_admin1_aliases_country_alias", table_name="admin1_aliases")
    op.drop_table("admin1_aliases")
    op.drop_index("ix_intensity_crisis_week_type", table_name="crisis_intensity_weekly")
    op.drop_index("ix_intensity_crisis_week", table_name="crisis_intensity_weekly")
    op.drop_table("crisis_intensity_weekly")
