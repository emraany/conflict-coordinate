"""entity_mentions table for NER output

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "entity_mentions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "event_id",
            sa.Integer(),
            sa.ForeignKey("crisis_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.Integer(),
            sa.ForeignKey("sources.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("label", sa.String(length=20), nullable=False),
        sa.Column("text", sa.String(length=200), nullable=False),
        sa.Column("text_norm", sa.String(length=200), nullable=False),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_entity_mentions_event_id", "entity_mentions", ["event_id"])
    op.create_index("ix_entity_mentions_source_id", "entity_mentions", ["source_id"])
    op.create_index(
        "ix_entity_mentions_label_norm", "entity_mentions", ["label", "text_norm"]
    )


def downgrade() -> None:
    op.drop_index("ix_entity_mentions_label_norm", table_name="entity_mentions")
    op.drop_index("ix_entity_mentions_source_id", table_name="entity_mentions")
    op.drop_index("ix_entity_mentions_event_id", table_name="entity_mentions")
    op.drop_table("entity_mentions")
