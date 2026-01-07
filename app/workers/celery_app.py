from celery import Celery
from kombu import Exchange, Queue

from app.config import settings

# Create Celery app
celery_app = Celery(
    "payment_gateway",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.tasks.deposit_tasks",
        "app.workers.tasks.withdrawal_tasks",
        "app.workers.tasks.webhook_tasks",
        "app.workers.tasks.dlq_tasks",
    ],
)

# Define exchanges
default_exchange = Exchange("default", type="direct")
dlq_exchange = Exchange("dlq", type="direct")

# Define queues with Dead Letter Queue (DLQ) support
celery_app.conf.task_queues = (
    # Main transaction queue
    Queue(
        "transactions",
        exchange=default_exchange,
        routing_key="transaction",
    ),
    # Dead Letter Queue for failed transactions
    Queue(
        "transactions.dlq",
        exchange=dlq_exchange,
        routing_key="transaction.failed",
        queue_arguments={
            "x-message-ttl": 86400000,  # 24 hours TTL for DLQ messages
            "x-max-length": 10000,  # Max 10k messages in DLQ
        },
    ),
    # webhook queue
    Queue(
        "webhooks",
        exchange=default_exchange,
        routing_key="webhook",
    ),
    # dead Letter Queue for failed webhooks
    Queue(
        "webhooks.dlq",
        exchange=dlq_exchange,
        routing_key="webhook.failed",
        queue_arguments={
            "x-message-ttl": 86400000,  # 24 hours TTL
            "x-max-length": 10000,
        },
    ),
    # legacy queues for backward compatibility
    Queue("deposits", exchange=default_exchange, routing_key="deposit"),
    Queue("withdrawals", exchange=default_exchange, routing_key="withdrawal"),
)

# configure celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,
    task_soft_time_limit=540,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    # DLQ settings
    task_default_queue="transactions",
    task_default_exchange="default",
    task_default_routing_key="transaction",
)

# Task routing
celery_app.conf.task_routes = {
    "app.workers.tasks.deposit_tasks.*": {"queue": "transactions"},
    "app.workers.tasks.withdrawal_tasks.*": {"queue": "transactions"},
    "app.workers.tasks.webhook_tasks.*": {"queue": "webhooks"},
    # DLQ tasks
    "app.workers.tasks.dlq_tasks.*": {"queue": "transactions.dlq"},
}
