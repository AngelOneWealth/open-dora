"""add full_name to users

Revision ID: i9e6a3c1d530
Revises: h8d5f2b0c419
Create Date: 2026-03-24 00:02:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "i9e6a3c1d530"
down_revision = "h8d5f2b0c419"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("full_name", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "full_name")
