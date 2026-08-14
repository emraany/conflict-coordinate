"""crisis_events lookup indexes — source_id (FK SET NULL) and external_id

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-13

Without ix_crisis_events_source_id, every `sources` row deletion scans the
whole events table for the ON DELETE SET NULL; external_id backs the
per-source dedupe lookups during attach.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_crisis_events_source_id "
        "ON crisis_events (source_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_crisis_events_external_id "
        "ON crisis_events (external_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_crisis_events_external_id")
    op.execute("DROP INDEX IF EXISTS ix_crisis_events_source_id")
