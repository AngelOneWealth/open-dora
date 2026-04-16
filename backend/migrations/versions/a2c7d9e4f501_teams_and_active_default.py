"""teams and active default false

Revision ID: a2c7d9e4f501
Revises: f6b3d8e0a291
Create Date: 2026-03-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a2c7d9e4f501"
down_revision: Union[str, None] = "f6b3d8e0a291"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create teams table
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # 2. Add team_id FK to users
    op.add_column(
        "users",
        sa.Column("team_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_team_id",
        "users", "teams",
        ["team_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_users_team_id", "users", ["team_id"])

    # 3. Change users.active server default to false
    op.alter_column("users", "active", server_default=sa.false())


def downgrade() -> None:
    op.alter_column("users", "active", server_default=sa.true())
    op.drop_index("ix_users_team_id", table_name="users")
    op.drop_constraint("fk_users_team_id", "users", type_="foreignkey")
    op.drop_column("users", "team_id")
    op.drop_table("teams")
