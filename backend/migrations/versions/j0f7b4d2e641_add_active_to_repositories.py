"""add active to repositories

Revision ID: j0f7b4d2e641
Revises: i9e6a3c1d530
Create Date: 2026-03-24 00:03:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "j0f7b4d2e641"
down_revision = "i9e6a3c1d530"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("repositories", sa.Column("active", sa.Boolean(), nullable=False, server_default="true"))


def downgrade() -> None:
    op.drop_column("repositories", "active")
