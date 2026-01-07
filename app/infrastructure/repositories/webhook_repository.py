import json
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.models import WebhookDelivery, WebhookDeliveryStatus
from app.infrastructure.repositories.base import BaseRepository


class WebhookRepository(BaseRepository[WebhookDelivery]):
    def __init__(self, db: Session):
        super().__init__(WebhookDelivery, db)

    def create_delivery(
        self,
        transaction_id: UUID,
        webhook_url: str,
        payload: dict,
        max_attempts: int = 5,
    ) -> WebhookDelivery:
        delivery = WebhookDelivery(
            transaction_id=transaction_id,
            webhook_url=webhook_url,
            payload=json.dumps(payload),
            status=WebhookDeliveryStatus.PENDING,
            attempt_count=0,
            max_attempts=max_attempts,
        )

        self.db.add(delivery)
        self.db.flush()
        self.db.refresh(delivery)

        return delivery

    def get_by_transaction_id(self, transaction_id: UUID) -> list[WebhookDelivery]:
        return (
            self.db.query(WebhookDelivery)
            .filter(WebhookDelivery.transaction_id == transaction_id)
            .order_by(WebhookDelivery.created_at.desc())
            .all()
        )

    def get_pending_deliveries(self, limit: int = 100) -> list[WebhookDelivery]:
        return (
            self.db.query(WebhookDelivery)
            .filter(WebhookDelivery.status == WebhookDeliveryStatus.PENDING)
            .filter(WebhookDelivery.attempt_count < WebhookDelivery.max_attempts)
            .order_by(WebhookDelivery.created_at.asc())
            .limit(limit)
            .all()
        )

    def mark_as_sending(self, delivery_id: UUID) -> WebhookDelivery | None:
        delivery = self.get_by_id(delivery_id)
        if delivery:
            delivery.status = WebhookDeliveryStatus.SENDING
            delivery.attempt_count = delivery.attempt_count + 1
            self.db.commit()
            self.db.refresh(delivery)
        return delivery

    def mark_as_success(
        self,
        delivery_id: UUID,
        http_status_code: int,
        response_body: str,
    ) -> WebhookDelivery | None:
        delivery = self.get_by_id(delivery_id)
        if delivery:
            delivery.status = WebhookDeliveryStatus.SUCCESS
            delivery.http_status_code = http_status_code
            delivery.response_body = response_body[:1000]
            self.db.commit()
            self.db.refresh(delivery)
        return delivery

    def mark_as_failed(
        self,
        delivery_id: UUID,
        error_message: str,
        http_status_code: int | None = None,
    ) -> WebhookDelivery | None:
        delivery = self.get_by_id(delivery_id)
        if delivery:
            delivery.status = WebhookDeliveryStatus.FAILED
            delivery.error_message = error_message[:1000]
            if http_status_code:
                delivery.http_status_code = http_status_code
            self.db.commit()
            self.db.refresh(delivery)
        return delivery
