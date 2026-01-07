from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import DECIMAL_PLACES, MAX_DIGITS
from app.infrastructure.database.base import GUID, BaseModel

if TYPE_CHECKING:
    from app.infrastructure.models.transaction import Transaction
    from app.infrastructure.models.user import User


class Account(BaseModel):
    __tablename__ = "accounts"

    user_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=MAX_DIGITS, scale=DECIMAL_PLACES),
        nullable=False,
        default=Decimal("0.00"),
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    user: Mapped["User"] = relationship("User", back_populates="account")
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction", back_populates="account", cascade="all, delete-orphan"
    )

    __table_args__ = (CheckConstraint("balance >= 0", name="balance_non_negative"),)

    def __repr__(self) -> str:
        return f"<Account(id={self.id}, user_id={self.user_id}, balance={self.balance} {self.currency})>"
