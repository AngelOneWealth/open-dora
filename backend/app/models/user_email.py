from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserEmail(Base):
    __tablename__ = "user_emails"

    id:      Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    email:   Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (UniqueConstraint("email", name="uq_user_emails_email"),)

    user: Mapped["User"] = relationship(back_populates="emails")  # noqa: F821
