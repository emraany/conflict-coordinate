"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Declare each enum once as a reusable object. create_type=False on every column
# that references them; we create the types explicitly below so there's no chance
# of auto-create firing twice.
crisis_status = postgresql.ENUM(
    "active", "frozen", "resolved", name="crisis_status", create_type=False
)
actor_role = postgresql.ENUM(
    "party", "mediator", "observer", "affected", name="actor_role", create_type=False
)
actor_type = postgresql.ENUM(
    "state", "non_state", "coalition", "other", name="actor_type", create_type=False
)
source_type = postgresql.ENUM(
    "news", "report", "academic", "official", "primary",
    name="source_type", create_type=False,
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    bind = op.get_bind()
    crisis_status.create(bind, checkfirst=True)
    actor_role.create(bind, checkfirst=True)
    actor_type.create(bind, checkfirst=True)
    source_type.create(bind, checkfirst=True)

    op.create_table(
        "crises",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False, unique=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("country", sa.String(length=120)),
        sa.Column("region", sa.String(length=120)),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("geom", Geometry(geometry_type="POINT", srid=4326)),
        sa.Column("summary", sa.Text()),
        sa.Column("status", crisis_status, nullable=False, server_default="active"),
        sa.Column("conflict_type", sa.String(length=80)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("last_event_at", sa.DateTime(timezone=True)),
        sa.Column("external_id", sa.String(length=200)),
        sa.Column("source_name", sa.String(length=80)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_crises_slug", "crises", ["slug"], unique=True)
    op.create_index("ix_crises_status", "crises", ["status"])
    op.create_index("ix_crises_external_id", "crises", ["external_id"])
    op.create_index("ix_crises_source_name", "crises", ["source_name"])
    op.create_index(
        "ix_crises_source_external",
        "crises",
        ["source_name", "external_id"],
        unique=True,
    )
    op.execute("CREATE INDEX ix_crises_geom ON crises USING GIST (geom)")

    op.create_table(
        "actors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("type", actor_type, nullable=False, server_default="other"),
        sa.Column("description", sa.Text()),
        sa.Column("wikipedia_url", sa.String(length=500)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_actors_name", "actors", ["name"])

    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "crisis_id",
            sa.Integer(),
            sa.ForeignKey("crises.id", ondelete="CASCADE"),
        ),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("publisher", sa.String(length=200)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("retrieved_at", sa.DateTime(timezone=True)),
        sa.Column("source_type", source_type, nullable=False, server_default="news"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_sources_crisis_id", "sources", ["crisis_id"])

    op.create_table(
        "crisis_actors",
        sa.Column(
            "crisis_id",
            sa.Integer(),
            sa.ForeignKey("crises.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "actor_id",
            sa.Integer(),
            sa.ForeignKey("actors.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("role", actor_role, nullable=False, server_default="party"),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "source_id",
            sa.Integer(),
            sa.ForeignKey("sources.id", ondelete="SET NULL"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "crisis_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "crisis_id",
            sa.Integer(),
            sa.ForeignKey("crises.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(length=80)),
        sa.Column("description", sa.Text()),
        sa.Column("fatalities", sa.Integer()),
        sa.Column("location_name", sa.String(length=200)),
        sa.Column("lat", sa.Float()),
        sa.Column("lng", sa.Float()),
        sa.Column("external_id", sa.String(length=200)),
        sa.Column(
            "source_id",
            sa.Integer(),
            sa.ForeignKey("sources.id", ondelete="SET NULL"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_events_crisis_id", "crisis_events", ["crisis_id"])
    op.create_index("ix_events_occurred_at", "crisis_events", ["occurred_at"])
    op.create_index("ix_events_external_id", "crisis_events", ["external_id"])
    op.create_index(
        "ix_events_crisis_occurred",
        "crisis_events",
        ["crisis_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_table("crisis_events")
    op.drop_table("crisis_actors")
    op.drop_table("sources")
    op.drop_table("actors")
    op.execute("DROP INDEX IF EXISTS ix_crises_geom")
    op.drop_table("crises")
    bind = op.get_bind()
    source_type.drop(bind, checkfirst=True)
    actor_type.drop(bind, checkfirst=True)
    actor_role.drop(bind, checkfirst=True)
    crisis_status.drop(bind, checkfirst=True)
