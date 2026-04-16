from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression

from app.database import Base


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    # owner column removed — derived from full_name via the property below
    organisation_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=expression.true(), default=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(511), unique=True, nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), default="main")
    commits_synced_at:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    prs_synced_at:        Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviews_synced_at:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pr_commits_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    organisation: Mapped[Organization | None] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Organization", back_populates="repositories"
    )
    commits: Mapped[list["Commit"]] = relationship(back_populates="repository")  # noqa: F821
    pull_requests: Mapped[list["PullRequest"]] = relationship(back_populates="repository")  # noqa: F821
    labels: Mapped[list["Label"]] = relationship(back_populates="repository")  # noqa: F821

    @property
    def owner(self) -> str:
        """Derived from full_name — keeps existing schemas/routers working unchanged."""
        return self.full_name.split("/")[0]
