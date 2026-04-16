"""per-phase synced_at on repositories

Revision ID: c7f3a2e5b918
Revises: a1c4e9f2d803
Create Date: 2026-03-19 18:00:00.000000

Replace the single `synced_at` column with four independent timestamps so
each sync phase (commits, PRs, reviews, PR-commits) can record its own
progress.  Existing `synced_at` values are copied into all four columns so
incremental syncs continue working without re-fetching everything.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7f3a2e5b918"
down_revision: Union[str, None] = "a1c4e9f2d803"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("repositories", sa.Column("commits_synced_at",    sa.DateTime(timezone=True), nullable=True))
    op.add_column("repositories", sa.Column("prs_synced_at",        sa.DateTime(timezone=True), nullable=True))
    op.add_column("repositories", sa.Column("reviews_synced_at",    sa.DateTime(timezone=True), nullable=True))
    op.add_column("repositories", sa.Column("pr_commits_synced_at", sa.DateTime(timezone=True), nullable=True))

    # Preserve existing sync progress so the next run stays incremental
    op.execute("""
        UPDATE repositories
        SET commits_synced_at    = synced_at,
            prs_synced_at        = synced_at,
            reviews_synced_at    = synced_at,
            pr_commits_synced_at = synced_at
    """)

    op.drop_column("repositories", "synced_at")


def downgrade() -> None:
    op.add_column("repositories", sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True))

    # Best-effort: restore synced_at as the latest timestamp across all phases
    op.execute("""
        UPDATE repositories
        SET synced_at = GREATEST(
            commits_synced_at,
            prs_synced_at,
            reviews_synced_at,
            pr_commits_synced_at
        )
    """)

    op.drop_column("repositories", "pr_commits_synced_at")
    op.drop_column("repositories", "reviews_synced_at")
    op.drop_column("repositories", "prs_synced_at")
    op.drop_column("repositories", "commits_synced_at")
