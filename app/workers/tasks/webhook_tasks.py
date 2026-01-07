import json
from uuid import UUID

import httpx
from celery import Task
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.infrastructure.database.session import SessionLocal
from app.infrastructure.models import WebhookDelivery, WebhookDeliveryStatus
from app.workers.base_task import DLQTask
from app.workers.celery_app import celery_app

logger = get_logger(__name__)

WEBHOOK_TIMEOUT_SECONDS = 30
WEBHOOK_MAX_RETRIES = 5
WEBHOOK_RETRY_BACKOFF = 2  # multiplier


class WebhookDeliveryTask(DLQTask):
    autoretry_for = (httpx.RequestError, httpx.HTTPStatusError)
    retry_kwargs = {"max_retries": WEBHOOK_MAX_RETRIES}
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True  # random? should I open this?


@celery_app.task(bind=True, base=WebhookDeliveryTask, name="send_webhook_notification")
def send_webhook_notification(
    self: Task,
    webhook_delivery_id: str,
) -> dict:
    db: Session = SessionLocal()

    try:
        delivery = (
            db.query(WebhookDelivery)
            .filter(WebhookDelivery.id == UUID(webhook_delivery_id))
            .first()
        )
        if not delivery:
            logger.error("webhook_delivery_not_found", delivery_id=webhook_delivery_id)
            return {"success": False, "error": "Webhook delivery not found"}

        delivery.attempt_count = delivery.attempt_count + 1
        delivery.status = WebhookDeliveryStatus.SENDING
        db.commit()
        logger.info(
            "webhook_sending",
            delivery_id=str(delivery.id),
            attempt=delivery.attempt_count,
            max_attempts=delivery.max_attempts,
            url=delivery.webhook_url,
        )

        with httpx.Client(timeout=WEBHOOK_TIMEOUT_SECONDS) as client:
            response = client.post(
                str(delivery.webhook_url),
                json=json.loads(str(delivery.payload)),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "PaymentGateway-Webhook/1.0",
                    "X-Webhook-Delivery-ID": str(delivery.id),
                },
            )

            if 500 <= response.status_code < 600:
                response.raise_for_status()

            delivery.http_status_code = response.status_code
            delivery.response_body = response.text[:1000]
            if 200 <= response.status_code < 300:
                delivery.status = WebhookDeliveryStatus.SUCCESS
                logger.info(
                    "webhook_delivered_successfully",
                    delivery_id=str(delivery.id),
                    status_code=response.status_code,
                )
            else:
                delivery.status = WebhookDeliveryStatus.FAILED
                delivery.error_message = f"HTTP {response.status_code}: {response.text[:500]}"
                logger.warning(
                    "webhook_permanent_failure",
                    delivery_id=str(delivery.id),
                    status_code=response.status_code,
                )
            db.commit()
            return {
                "success": delivery.status == WebhookDeliveryStatus.SUCCESS,
                "http_status_code": response.status_code,
                "response": response.text[:200],
            }

    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        logger.warning(
            "webhook_delivery_error_will_retry",
            delivery_id=webhook_delivery_id,
            error=str(exc),
            attempt=self.request.retries + 1,
            max_retries=WEBHOOK_MAX_RETRIES,
        )
        delivery = (
            db.query(WebhookDelivery)
            .filter(WebhookDelivery.id == UUID(webhook_delivery_id))
            .first()
        )
        if delivery:
            delivery.error_message = str(exc)[:500]
            if self.request.retries >= WEBHOOK_MAX_RETRIES - 1:
                delivery.status = WebhookDeliveryStatus.FAILED
                logger.error(
                    "webhook_delivery_failed_max_retries",
                    delivery_id=webhook_delivery_id,
                    error=str(exc),
                )
            else:
                delivery.status = WebhookDeliveryStatus.PENDING
            db.commit()
        raise

    except Exception as e:
        logger.error(
            "webhook_delivery_unexpected_error",
            delivery_id=webhook_delivery_id,
            error=str(e),
        )
        delivery = (
            db.query(WebhookDelivery)
            .filter(WebhookDelivery.id == UUID(webhook_delivery_id))
            .first()
        )
        if delivery:
            delivery.status = WebhookDeliveryStatus.FAILED
            delivery.error_message = f"Unexpected error: {str(e)[:500]}"
            db.commit()
        return {"success": False, "error": str(e)}
    finally:
        db.close()
