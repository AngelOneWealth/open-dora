"""initial schema

Revision ID: b361d83c6aa4
Revises:
Create Date: 2026-03-19 08:19:03.150236

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b361d83c6aa4'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── repositories ────────────────────────────────────────────
    op.create_table(
        "repositories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(511), nullable=False),
        sa.Column("default_branch", sa.String(255), nullable=False, server_default="main"),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("github_id", name="uq_repositories_github_id"),
        sa.UniqueConstraint("full_name", name="uq_repositories_full_name"),
    )

    # ── users ────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("login", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("avatar_url", sa.String(2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("github_id", name="uq_users_github_id"),
        sa.UniqueConstraint("login", name="uq_users_login"),
    )

    # ── commits ──────────────────────────────────────────────────
    op.create_table(
        "commits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sha", sa.String(40), nullable=False),
        sa.Column("repository_id", sa.Integer(), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("committer_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("additions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deletions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("authored_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("sha", name="uq_commits_sha"),
    )
    op.create_index("ix_commits_repo_authored_at", "commits", ["repository_id", "authored_at"])
    op.create_index("ix_commits_author_authored_at", "commits", ["author_id", "authored_at"])
    op.create_index("ix_commits_committer_id", "commits", ["committer_id"])

    # ── pull_requests ─────────────────────────────────────────────
    op.create_table(
        "pull_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("repository_id", sa.Integer(), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("state", sa.String(10), nullable=False, server_default="open"),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("base_branch", sa.String(255), nullable=False),
        sa.Column("head_branch", sa.String(255), nullable=False),
        sa.Column("head_sha", sa.String(40), nullable=False),
        sa.Column("merge_commit_sha", sa.String(40), nullable=True),
        sa.Column("draft", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("additions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deletions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("changed_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("commits_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("github_id", name="uq_pr_github_id"),
        sa.UniqueConstraint("repository_id", "number", name="uq_pr_repo_number"),
    )
    op.create_index("ix_pr_repo_base_branch_merged_at", "pull_requests", ["repository_id", "base_branch", "merged_at"])
    op.create_index("ix_pr_repo_opened_at", "pull_requests", ["repository_id", "opened_at"])
    op.create_index("ix_pr_repo_state", "pull_requests", ["repository_id", "state"])
    op.create_index("ix_pr_author_id", "pull_requests", ["author_id"])

    # ── pr_commits (junction) ────────────────────────────────────
    op.create_table(
        "pr_commits",
        sa.Column("pull_request_id", sa.Integer(), sa.ForeignKey("pull_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("commit_id", sa.Integer(), sa.ForeignKey("commits.id", ondelete="CASCADE"), nullable=False),
        sa.PrimaryKeyConstraint("pull_request_id", "commit_id"),
    )
    op.create_index("ix_pr_commits_commit_id", "pr_commits", ["commit_id"])

    # ── labels ────────────────────────────────────────────────────
    op.create_table(
        "labels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("repository_id", sa.Integer(), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("color", sa.String(6), nullable=True),
        sa.UniqueConstraint("repository_id", "name", name="uq_label_repo_name"),
    )

    # ── pr_labels (junction) ─────────────────────────────────────
    op.create_table(
        "pr_labels",
        sa.Column("pull_request_id", sa.Integer(), sa.ForeignKey("pull_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label_id", sa.Integer(), sa.ForeignKey("labels.id", ondelete="CASCADE"), nullable=False),
        sa.PrimaryKeyConstraint("pull_request_id", "label_id"),
    )
    op.create_index("ix_pr_labels_label_id", "pr_labels", ["label_id"])

    # ── reviews ───────────────────────────────────────────────────
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("pull_request_id", sa.Integer(), sa.ForeignKey("pull_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("github_id", name="uq_reviews_github_id"),
    )
    op.create_index("ix_reviews_pr_submitted_at", "reviews", ["pull_request_id", "submitted_at"])
    op.create_index("ix_reviews_pr_state", "reviews", ["pull_request_id", "state"])
    op.create_index("ix_reviews_reviewer_id", "reviews", ["reviewer_id"])


def downgrade() -> None:
    op.drop_table("reviews")
    op.drop_table("pr_labels")
    op.drop_table("labels")
    op.drop_table("pr_commits")
    op.drop_table("pull_requests")
    op.drop_table("commits")
    op.drop_table("users")
    op.drop_table("repositories")
