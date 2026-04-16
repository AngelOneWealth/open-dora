"""add net_lines to commits

Revision ID: d4e8b1f3c029
Revises: c7f3a2e5b918
Create Date: 2026-03-21 00:00:00.000000

Add a stored `net_lines` column (additions - deletions) to the commits table
and backfill all existing rows so queries and the user-detail API can use it
directly without computing it on the fly.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e8b1f3c029"
down_revision: Union[str, None] = "c7f3a2e5b918"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("commits", sa.Column("net_lines", sa.Integer(), nullable=False, server_default="0"))
    # Backfill all existing rows
    op.execute("UPDATE commits SET net_lines = additions - deletions")


def downgrade() -> None:
    op.drop_column("commits", "net_lines")
