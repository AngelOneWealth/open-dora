"""add active to users

Revision ID: f6b3d8e0a291
Revises: e5a9c2f1b047
Create Date: 2026-03-22 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "f6b3d8e0a291"
down_revision = "e5a9c2f1b047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("users", "active")
