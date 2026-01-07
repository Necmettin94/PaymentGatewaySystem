from datetime import UTC, datetime

from celery import Task

from app.core.logging import get_logger
from app.infrastructure.database.session import SessionLocal

logger = get_logger(__name__)


class DatabaseTask(Task):
    @staticmethod
    def get_db():
        db = SessionLocal()
        db.expire_all()  # Force fresh reads from DB (avoid stale cache)
        return db


class DLQTask(Task):
    @staticmethod
    def get_db():
        db = SessionLocal()
        db.expire_all()  # Force fresh reads from DB (avoid stale cache)
        return db

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        if self.request.retries >= self.max_retries:
            logger.error(
                "task_failed_max_retries_sending_to_dlq",
                task_id=task_id,
                task_name=self.name,
                retries=self.request.retries,
                max_retries=self.max_retries,
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )

            dlq_message = {
                "task_id": task_id,
                "task_name": self.name,
                "args": args,
                "kwargs": kwargs,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
                "traceback": str(einfo),
                "failed_at": datetime.now(UTC).isoformat(),
                "retry_count": self.request.retries,
            }

            try:
                if "webhook" in self.name.lower():
                    dlq_queue = "webhooks.dlq"
                else:
                    dlq_queue = "transactions.dlq"

                self.app.send_task(
                    "app.workers.tasks.dlq_tasks.handle_failed_task",
                    args=[dlq_message],
                    queue=dlq_queue,
                    routing_key=(
                        "transaction.failed"
                        if dlq_queue == "transactions.dlq"
                        else "webhook.failed"
                    ),
                )

                logger.info(
                    "task_sent_to_dlq",
                    task_id=task_id,
                    task_name=self.name,
                    dlq_queue=dlq_queue,
                )

            except Exception as dlq_error:
                # If DLQ send fails, log critical error
                logger.critical(
                    "failed_to_send_to_dlq",
                    task_id=task_id,
                    task_name=self.name,
                    dlq_error=str(dlq_error),
                    original_exception=str(exc),
                )

        else:
            logger.warning(
                "task_failed_will_retry",
                task_id=task_id,
                task_name=self.name,
                attempt=self.request.retries + 1,
                max_retries=self.max_retries,
                exception=str(exc),
            )
