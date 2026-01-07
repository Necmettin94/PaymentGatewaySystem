from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import BaseModel


class WebhookDeliveryStatus:
    PENDING = "PENDING"  # Waiting to be sent
    SENDING = "SENDING"  # Currently being sent
    SUCCESS = "SUCCESS"  # Successfully delivered
    FAILED = "FAILED"  # Failed after all retries


class WebhookDelivery(BaseModel):
    __tablename__ = "webhook_deliveries"

    transaction_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False
    )

    webhook_url: Mapped[str] = mapped_column(String(2048), nullable=False)

    status: Mapped[str] = mapped_column(
        Enum(
            WebhookDeliveryStatus.PENDING,
            WebhookDeliveryStatus.SENDING,
            WebhookDeliveryStatus.SUCCESS,
            WebhookDeliveryStatus.FAILED,
            name="webhook_delivery_status",
        ),
        nullable=False,
        default=WebhookDeliveryStatus.PENDING,
        index=True,
    )

    # Retry tracking
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)  # Max 5 retries

    # Response tracking
    http_status_code: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # HTTP response code
    response_body: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Response body (truncated)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)  # Error details

    # Payload sent (JSON)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON payload sent to webhook

    def __repr__(self) -> str:
        return (
            f"<WebhookDelivery(id={self.id}, transaction_id={self.transaction_id}, "
            f"status={self.status}, attempt={self.attempt_count}/{self.max_attempts})>"
        )
