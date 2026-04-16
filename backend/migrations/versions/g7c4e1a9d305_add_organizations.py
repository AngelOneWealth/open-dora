"""add organizations table

Revision ID: g7c4e1a9d305
Revises: f6b3d8e0a291
Create Date: 2026-03-24 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "g7c4e1a9d305"
down_revision = "a2c7d9e4f501"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id",           sa.Integer(),              nullable=False),
        sa.Column("login",        sa.String(255),            nullable=False),
        sa.Column("display_name", sa.String(255),            nullable=True),
        sa.Column("avatar_url",   sa.String(1024),           nullable=True),
        sa.Column("github_token", sa.Text(),                 nullable=False),
        sa.Column("created_at",   sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at",   sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("login", name="uq_organizations_login"),
    )


def downgrade() -> None:
    op.drop_table("organizations")
