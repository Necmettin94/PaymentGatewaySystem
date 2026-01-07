from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import DECIMAL_PLACES, MAX_DIGITS
from app.infrastructure.database.base import GUID, BaseModel

if TYPE_CHECKING:
    from app.infrastructure.models.account import Account


class Transaction(BaseModel):
    __tablename__ = "transactions"

    account_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transaction_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # DEPOSIT | WITHDRAWAL
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=MAX_DIGITS, scale=DECIMAL_PLACES),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)

    bank_transaction_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )  # External bank reference
    bank_response: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Raw bank response for debugging

    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    idempotency_key: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )  # Links to original request
    celery_task_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )  # Tracks Celery task

    account: Mapped["Account"] = relationship("Account", back_populates="transactions")

    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        # Composite indexes for common query patterns
        Index("idx_account_status_created", "account_id", "status", "created_at"),
        Index("idx_account_type_created", "account_id", "transaction_type", "created_at"),
        # Additional indexes are created via migration:
        # - idx_unique_idempotency_key: Unique partial index for idempotency
        # - idx_status_created_desc: Status + created_at DESC for filtering
        # - idx_account_created_desc: Account + created_at DESC for history
        # - idx_created_desc: Recent transactions across all accounts
        # - idx_type_status: Transaction type + status filtering
    )

    def __repr__(self) -> str:
        return (
            f"<Transaction(id={self.id}, type={self.transaction_type}, "
            f"amount={self.amount} {self.currency}, status={self.status})>"
        )
