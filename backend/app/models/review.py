from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ReviewState(str, Enum):
    approved = "approved"
    changes_requested = "changes_requested"
    commented = "commented"
    dismissed = "dismissed"


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        # Populate first_review_at: earliest review per PR, ordered by time
        Index("ix_reviews_pr_submitted_at", "pull_request_id", "submitted_at"),
        # Filter approvals per PR (change failure rate, approval rate)
        Index("ix_reviews_pr_state", "pull_request_id", "state"),
        # FK index for reviewer lookups
        Index("ix_reviews_reviewer_id", "reviewer_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    pull_request_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id"), nullable=False)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    state: Mapped[ReviewState] = mapped_column(String(20), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    pull_request: Mapped["PullRequest"] = relationship(back_populates="reviews")  # noqa: F821
    reviewer: Mapped["User | None"] = relationship(back_populates="reviews")  # noqa: F821
