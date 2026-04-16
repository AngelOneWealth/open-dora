from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.sql import expression
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    login: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(2048))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=expression.false(), default=False)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    team: Mapped["Team | None"] = relationship("Team", back_populates="users")  # noqa: F821
    emails: Mapped[list["UserEmail"]] = relationship("UserEmail", back_populates="user", cascade="all, delete-orphan")  # noqa: F821

    authored_commits: Mapped[list["Commit"]] = relationship(foreign_keys="Commit.author_id", back_populates="author")  # noqa: F821
    committed_commits: Mapped[list["Commit"]] = relationship(foreign_keys="Commit.committer_id", back_populates="committer")  # noqa: F821
    pull_requests: Mapped[list["PullRequest"]] = relationship(foreign_keys="PullRequest.author_id", back_populates="author")  # noqa: F821
    reviews: Mapped[list["Review"]] = relationship(back_populates="reviewer")  # noqa: F821
