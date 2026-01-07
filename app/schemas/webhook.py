from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import BankResponseStatus


class BankCallbackPayload(BaseModel):
    transaction_id: UUID = Field(..., description="Internal transaction ID")
    bank_transaction_id: str | None = Field(None, description="Bank's transaction reference")
    status: BankResponseStatus = Field(..., description="Bank processing status")
    message: str | None = Field(None, description="Bank response message")
    error_code: str | None = Field(None, description="Error code if failed")
    timestamp: int = Field(
        ...,
        description="Unix timestamp of the webhook event (prevents replay attacks)",
    )


class WebhookResponse(BaseModel):
    received: bool = True
    message: str = "Webhook received and queued for processing"


class WebhookDeliveryResponse(BaseModel):
    id: UUID
    transaction_id: UUID
    webhook_url: str
    status: str
    attempt_count: int
    max_attempts: int
    http_status_code: int | None = None
    response_body: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WebhookDeliveryListResponse(BaseModel):
    deliveries: list[WebhookDeliveryResponse]
    total: int = Field(..., description="Total number of deliveries")
