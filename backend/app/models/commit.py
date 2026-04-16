from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Commit(Base):
    __tablename__ = "commits"
    __table_args__ = (
        # Lead time: fetch commits for a repo within a time window
        Index("ix_commits_repo_authored_at", "repository_id", "authored_at"),
        # Per-author activity queries
        Index("ix_commits_author_authored_at", "author_id", "authored_at"),
        # FK indexes (Postgres does not auto-create these)
        Index("ix_commits_committer_id", "committer_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sha: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    committer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # Raw git identity — always populated regardless of GitHub account linkage.
    # Useful for display when author_id / committer_id is null.
    author_name: Mapped[str | None] = mapped_column(String(255))
    author_email: Mapped[str | None] = mapped_column(String(255))
    committer_name: Mapped[str | None] = mapped_column(String(255))
    committer_email: Mapped[str | None] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    additions: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)
    net_lines: Mapped[int] = mapped_column(Integer, default=0)  # additions - deletions
    authored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    repository: Mapped["Repository"] = relationship(back_populates="commits")  # noqa: F821
    author: Mapped["User | None"] = relationship(foreign_keys=[author_id], back_populates="authored_commits")  # noqa: F821
    committer: Mapped["User | None"] = relationship(foreign_keys=[committer_id], back_populates="committed_commits")  # noqa: F821
    pull_request_links: Mapped[list["PullRequestCommit"]] = relationship(back_populates="commit")  # noqa: F821
