from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import BaseModel

if TYPE_CHECKING:
    from app.infrastructure.models.account import Account


class User(BaseModel):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    webhook_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    account: Mapped[Optional["Account"]] = relationship(
        "Account", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"
