from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, PrimaryKeyConstraint, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PRState(str, Enum):
    open = "open"
    closed = "closed"
    merged = "merged"


class PullRequest(Base):
    __tablename__ = "pull_requests"
    __table_args__ = (
        # GitHub PR number is unique per repo
        UniqueConstraint("repository_id", "number", name="uq_pr_repo_number"),
        # Deployment frequency: merged PRs into a branch over time
        Index("ix_pr_repo_base_branch_merged_at", "repository_id", "base_branch", "merged_at"),
        # Lead time: PRs opened in a time window per repo
        Index("ix_pr_repo_opened_at", "repository_id", "opened_at"),
        # General state filter per repo (e.g. open PRs)
        Index("ix_pr_repo_state", "repository_id", "state"),
        # Per-author PR history
        Index("ix_pr_author_id", "author_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[PRState] = mapped_column(String(10), nullable=False, default=PRState.open)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    base_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    head_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    head_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    merge_commit_sha: Mapped[str | None] = mapped_column(String(40))
    draft: Mapped[bool] = mapped_column(Boolean, default=False)
    additions: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)
    changed_files: Mapped[int] = mapped_column(Integer, default=0)
    commits_count: Mapped[int] = mapped_column(Integer, default=0)
    # Denormalized for fast DORA lead-time queries
    first_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    repository: Mapped["Repository"] = relationship(back_populates="pull_requests")  # noqa: F821
    author: Mapped["User | None"] = relationship(foreign_keys=[author_id], back_populates="pull_requests")  # noqa: F821
    commits: Mapped[list["PullRequestCommit"]] = relationship(back_populates="pull_request")
    reviews: Mapped[list["Review"]] = relationship(back_populates="pull_request")  # noqa: F821
    labels: Mapped[list["PullRequestLabel"]] = relationship(back_populates="pull_request")


class PullRequestCommit(Base):
    __tablename__ = "pr_commits"
    __table_args__ = (
        PrimaryKeyConstraint("pull_request_id", "commit_id"),
        # Reverse lookup: which PRs contain this commit
        Index("ix_pr_commits_commit_id", "commit_id"),
    )

    pull_request_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id"), nullable=False)
    commit_id: Mapped[int] = mapped_column(ForeignKey("commits.id"), nullable=False)

    pull_request: Mapped["PullRequest"] = relationship(back_populates="commits")
    commit: Mapped["Commit"] = relationship(back_populates="pull_request_links")  # noqa: F821


class Label(Base):
    __tablename__ = "labels"
    __table_args__ = (
        # Label names are unique per repo
        UniqueConstraint("repository_id", "name", name="uq_label_repo_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    color: Mapped[str | None] = mapped_column(String(6))

    repository: Mapped["Repository"] = relationship(back_populates="labels")  # noqa: F821
    pull_requests: Mapped[list["PullRequestLabel"]] = relationship(back_populates="label")


class PullRequestLabel(Base):
    __tablename__ = "pr_labels"
    __table_args__ = (
        PrimaryKeyConstraint("pull_request_id", "label_id"),
        # Reverse lookup: all PRs with a given label
        Index("ix_pr_labels_label_id", "label_id"),
    )

    pull_request_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id"), nullable=False)
    label_id: Mapped[int] = mapped_column(ForeignKey("labels.id"), nullable=False)

    pull_request: Mapped["PullRequest"] = relationship(back_populates="labels")
    label: Mapped["Label"] = relationship(back_populates="pull_requests")
