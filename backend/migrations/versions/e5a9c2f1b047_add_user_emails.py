"""add user_emails table

Revision ID: e5a9c2f1b047
Revises: d4e8b1f3c029
Create Date: 2026-03-22 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "e5a9c2f1b047"
down_revision = "d4e8b1f3c029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_emails",
        sa.Column("id",      sa.Integer,     nullable=False),
        sa.Column("user_id", sa.Integer,     nullable=False),
        sa.Column("email",   sa.String(255), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_user_emails_email"),
    )
    op.create_index("ix_user_emails_user_id", "user_emails", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_emails_user_id", table_name="user_emails")
    op.drop_table("user_emails")
