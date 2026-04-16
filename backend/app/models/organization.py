from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Organization(Base):
    __tablename__ = "organizations"

    id:           Mapped[int]        = mapped_column(primary_key=True)
    login:        Mapped[str]        = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    avatar_url:   Mapped[str | None] = mapped_column(String(1024))
    github_token: Mapped[str]        = mapped_column(Text, nullable=False)
    created_at:   Mapped[datetime]   = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:   Mapped[datetime]   = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    repositories: Mapped[list[Repository]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Repository", back_populates="organisation"
    )
