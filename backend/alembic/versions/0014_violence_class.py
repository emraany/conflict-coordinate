"""crises violence class

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-02

`crises.violence_class` records what kind of violence a region is currently
seeing — armed_conflict | criminal_violence | unrest | unclear — so the globe
can stop rendering a cartel shootout and a frontline the same way.
`violence_class_basis` is the derived evidence for that label (actor names
and event-type shares), shown in the dossier so the call is auditable.

Both are written once per ingest by
`app.ingestion.runner._classify_violence`, alongside the `violence_4w_*`
rollup, using the rules in `app.conflicts.violence_class`.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("crises", sa.Column("violence_class", sa.String(24), nullable=True))
    op.add_column(
        "crises", sa.Column("violence_class_basis", sa.String(400), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("crises", "violence_class_basis")
    op.drop_column("crises", "violence_class")
