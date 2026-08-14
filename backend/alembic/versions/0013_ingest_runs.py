"""ingest_runs — durable record of every ingest attempt

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-14

Ingest currently leaves no persistent trace: `_ingest_status` in the API
process is in-memory and the cron worker writes nothing at all. Once the
schedule runs unattended, a stalled pipeline is indistinguishable from a
quiet week — the globe keeps serving stale aggregates either way. This
table is what `/api/health` reads to tell the two apart.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingest_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "trigger", sa.String(length=16), nullable=False, server_default="cron"
        ),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingest_runs_finished_at", "ingest_runs", ["finished_at"])


def downgrade() -> None:
    op.drop_index("ix_ingest_runs_finished_at", table_name="ingest_runs")
    op.drop_table("ingest_runs")
