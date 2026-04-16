"""add raw author fields to commits

Revision ID: a1c4e9f2d803
Revises: b361d83c6aa4
Create Date: 2026-03-19 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c4e9f2d803"
down_revision: Union[str, None] = "b361d83c6aa4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("commits", sa.Column("author_name", sa.String(255), nullable=True))
    op.add_column("commits", sa.Column("author_email", sa.String(255), nullable=True))
    op.add_column("commits", sa.Column("committer_name", sa.String(255), nullable=True))
    op.add_column("commits", sa.Column("committer_email", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("commits", "committer_email")
    op.drop_column("commits", "committer_name")
    op.drop_column("commits", "author_email")
    op.drop_column("commits", "author_name")
