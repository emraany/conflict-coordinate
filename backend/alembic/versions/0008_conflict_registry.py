"""conflict registry tables + crises.legacy + crisis_events.conflict_id

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-19

Foundation for the conflict-registry rebuild. A `Conflict` becomes the entity
a dot represents on the globe; `crises` rows (admin1 activity cells) are
flagged `legacy=true` and hidden from the public API once routing lands.

Additive only: no data movement, no drops. The old `crises` view still works
until Phase 4 cuts the API surface over.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # conflict_status enum — superset of crisis_status so 'emerging' (auto-
    # discovered, not yet activity-confirmed) is representable. We deliberately
    # do not reuse the existing crisis_status enum because the conflict layer
    # is a different domain. Created implicitly by the create_table below.
    conflict_status = sa.Enum(
        "active",
        "frozen",
        "resolved",
        "emerging",
        name="conflict_status",
    )

    op.create_table(
        "conflicts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("conflict_type", sa.String(length=80), nullable=True),
        sa.Column(
            "status",
            conflict_status,
            nullable=False,
            server_default="emerging",
        ),
        sa.Column("primary_iso3", sa.String(length=3), nullable=True),
        sa.Column(
            "secondary_iso3s",
            sa.ARRAY(sa.String(length=3)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column(
            "geom",
            Geometry(geometry_type="POINT", srid=4326),
            nullable=True,
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("wikipedia_url", sa.String(length=500), nullable=True),
        sa.Column("ucdp_conflict_id", sa.String(length=40), nullable=True),
        # yaml | wiki-auto | ucdp-auto | admin
        sa.Column(
            "registry_source",
            sa.String(length=20),
            nullable=False,
            server_default="yaml",
        ),
        sa.Column(
            "admin_curated",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "intensity_4w_events",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "intensity_4w_fatalities",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_conflicts_slug", "conflicts", ["slug"], unique=True)
    op.create_index("ix_conflicts_status", "conflicts", ["status"])
    op.create_index("ix_conflicts_primary_iso3", "conflicts", ["primary_iso3"])
    op.create_index(
        "ix_conflicts_ucdp_id",
        "conflicts",
        ["ucdp_conflict_id"],
        postgresql_where=sa.text("ucdp_conflict_id IS NOT NULL"),
    )

    op.create_table(
        "conflict_footprints",
        sa.Column(
            "conflict_id",
            sa.Integer(),
            sa.ForeignKey("conflicts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("country_iso3", sa.String(length=3), primary_key=True),
        sa.Column("admin1_norm", sa.String(length=120), primary_key=True),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default="1.0",
        ),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_footprints_iso3_admin1",
        "conflict_footprints",
        ["country_iso3", "admin1_norm"],
    )

    op.create_table(
        "conflict_parties",
        sa.Column(
            "conflict_id",
            sa.Integer(),
            sa.ForeignKey("conflicts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "actor_id",
            sa.Integer(),
            sa.ForeignKey("actors.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        # Reuse actor_role enum from 0001 — postgresql.ENUM with
        # create_type=False is the canonical way to reference an existing PG
        # enum from Alembic without re-emitting CREATE TYPE.
        sa.Column(
            "role",
            postgresql.ENUM(
                "party",
                "mediator",
                "observer",
                "affected",
                name="actor_role",
                create_type=False,
            ),
            nullable=False,
            server_default="party",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "source_id",
            sa.Integer(),
            sa.ForeignKey("sources.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "admin_curated",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "conflict_routing_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "conflict_id",
            sa.Integer(),
            sa.ForeignKey("conflicts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # actor | admin1 | country
        sa.Column("rule_type", sa.String(length=20), nullable=False),
        # Pattern semantics depend on rule_type. For actor: SQL LIKE pattern
        # matched against actor1/actor2/assoc_actor_*. For admin1:
        # "<iso3>:<admin1_norm>". For country: "<iso3>".
        sa.Column("pattern", sa.String(length=400), nullable=False),
        # Lower priority numbers win first when multiple rules match. Actor
        # rules typically priority=1, admin1=2, country=3.
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            server_default="100",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_routing_conflict",
        "conflict_routing_rules",
        ["conflict_id"],
    )
    op.create_index(
        "ix_routing_rule_type",
        "conflict_routing_rules",
        ["rule_type"],
    )

    # Legacy flag on the old admin1-keyed crises. Default false so existing
    # data and tests are unaffected until the backfill flips them.
    op.add_column(
        "crises",
        sa.Column(
            "legacy",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.create_index("ix_crises_legacy", "crises", ["legacy"])

    # conflict_id FK on events. Nullable for now — events not yet routed
    # (or genuinely orphan) keep NULL and stay queryable.
    op.add_column(
        "crisis_events",
        sa.Column(
            "conflict_id",
            sa.Integer(),
            sa.ForeignKey("conflicts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_events_conflict_id",
        "crisis_events",
        ["conflict_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_events_conflict_id", table_name="crisis_events")
    op.drop_column("crisis_events", "conflict_id")
    op.drop_index("ix_crises_legacy", table_name="crises")
    op.drop_column("crises", "legacy")

    op.drop_index("ix_routing_rule_type", table_name="conflict_routing_rules")
    op.drop_index("ix_routing_conflict", table_name="conflict_routing_rules")
    op.drop_table("conflict_routing_rules")

    op.drop_table("conflict_parties")

    op.drop_index("ix_footprints_iso3_admin1", table_name="conflict_footprints")
    op.drop_table("conflict_footprints")

    op.drop_index("ix_conflicts_ucdp_id", table_name="conflicts")
    op.drop_index("ix_conflicts_primary_iso3", table_name="conflicts")
    op.drop_index("ix_conflicts_status", table_name="conflicts")
    op.drop_index("ix_conflicts_slug", table_name="conflicts")
    op.drop_table("conflicts")

    sa.Enum(name="conflict_status").drop(op.get_bind(), checkfirst=True)
