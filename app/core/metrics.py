from prometheus_client import Counter, Gauge, Histogram

# api metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0),
)

# Transaction metric
transactions_total = Counter(
    "transactions_total",
    "Total number of transactions",
    ["type", "status"],
)

transaction_amount = Histogram(
    "transaction_amount_usd",
    "Transaction amount in USD",
    ["type"],
    buckets=(10, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000),
)

transaction_processing_duration_seconds = Histogram(
    "transaction_processing_duration_seconds",
    "Time taken to process a transaction",
    ["type"],
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

# active transactions
active_transactions = Gauge(
    "active_transactions",
    "Number of currently active transactions",
    ["type", "status"],
)

# balance metrics
account_balance = Histogram(
    "account_balance_usd",
    "Account balance in USD",
    buckets=(0, 100, 500, 1000, 5000, 10000, 25000, 50000, 100000),
)

# webhook metrics
webhooks_sent_total = Counter(
    "webhooks_sent_total",
    "Total number of webhooks sent",
    ["status"],
)

webhook_delivery_duration_seconds = Histogram(
    "webhook_delivery_duration_seconds",
    "Time taken to deliver a webhook",
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

webhook_retry_count = Counter(
    "webhook_retry_count",
    "Number of webhook retry attempts",
    ["final_status"],
)

# celery  metrics
celery_tasks_total = Counter(
    "celery_tasks_total",
    "Total number of Celery tasks",
    ["task_name", "status"],
)

celery_task_duration_seconds = Histogram(
    "celery_task_duration_seconds",
    "Celery task execution duration",
    ["task_name"],
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

# database netrics
db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query execution duration",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

db_connections_active = Gauge(
    "db_connections_active",
    "Number of active database connections",
)

# cache metrics
cache_operations_total = Counter(
    "cache_operations_total",
    "Total number of cache operations",
    ["operation", "status"],
)

cache_hit_ratio = Gauge(
    "cache_hit_ratio",
    "Cache hit ratio",
)

# business metrics
failed_transactions_total = Counter(
    "failed_transactions_total",
    "Total number of failed transactions",
    ["type", "error_code"],
)

pending_review_transactions = Gauge(
    "pending_review_transactions",
    "Number of transactions pending manual review",
)

insufficient_balance_errors = Counter(
    "insufficient_balance_errors_total",
    "Number of insufficient balance errors",
)

# rate limiting metrics
rate_limit_exceeded_total = Counter(
    "rate_limit_exceeded_total",
    "Number of times rate limit was exceeded",
    ["endpoint"],
)
