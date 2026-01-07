# Payment Gateway System

Asynchronous payment gateway handling deposits and withdrawals with proper consistency guarantees. Built for a technical assessment focusing on distributed systems patterns and production-ready practices.

## Tech Stack

FastAPI · PostgreSQL · SQLAlchemy · Celery · RabbitMQ · Redis · Docker

## Quick Start

```bash
cp .env.example .env
make up        # Start services
make migrate   # Run migrations
make seed      # Create test data (optional)
```

**Services:**
- API Docs: http://localhost:8000/docs
- Admin Panel: http://localhost:8000/admin
- Flower (Celery monitoring): http://localhost:5555
- RabbitMQ Management: http://localhost:15672 (guest/guest)

See `CREDENTIALS.md` for test accounts and Postman collection in `docs/`.

## How It Works

**Flow:** Client sends deposit/withdrawal → FastAPI validates & queues Celery task (202 Accepted) → Worker processes with distributed lock → Bank simulator responds (2-10s delay, 90% success) → Balance updated atomically → Webhook sent

**Transaction States:** PENDING → PROCESSING → SUCCESS/FAILED

**Data Model:**
```
User → Account → Transactions
                 └─ idempotency_key (unique)
                 └─ status, amount, type
```

## Key Design Decisions

### 1. Idempotency (Mandatory per task requirements)

**Problem:** Network failures cause duplicate requests.

**Solution:**
- Mandatory `Idempotency-Key` header for POST /deposits and /withdrawals
- Keys cached in Redis (24h TTL), DB constraint as fallback
- Subsequent requests with same key return cached response

**Implementation:** `app/api/middleware/idempotency.py`

### 2. Rate Limiting (Per task requirements)

**Strategy:** Token bucket algorithm in Redis

**Limits:**
- Balance endpoint: 10 req/min per user
- Transaction list: 20 req/min per user
- Global API: 1000 req/min

**Response headers:** `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`

**Implementation:** `app/api/middleware/rate_limit.py`

### 3. Data Consistency

**Challenge:** Prevent race conditions during concurrent balance updates.

**Solution: Hybrid Locking**

```python
# Distributed lock (Redis) + Pessimistic lock (DB)
async with distributed_lock(redis, f"account:{account_id}", ttl=10):
    async with db.begin():
        account = await db.execute(
            select(Account).where(Account.id == account_id).with_for_update()
        )
        account.balance += amount
```

**Why both?**
- Redis lock: Coordinates across multiple workers/API instances
- DB lock (`SELECT FOR UPDATE`): Prevents concurrent transactions within database
- READ COMMITTED isolation level: Balances performance vs. safety

**Implementation:** `app/domain/services/base_transaction_service.py`

### 4. Error Handling & Resilience

**Bank Simulator (per task requirements):**
- 90% success rate (configurable)
- Random delays: 2-10 seconds
- Error types: TIMEOUT, UNAVAILABLE, INSUFFICIENT_FUNDS

**Retry Strategy:**
- Celery exponential backoff: max 4 attempts
- Attempt 2: ~4s, Attempt 3: ~16s, Attempt 4: ~64s

**Circuit Breaker:** Opens after 5 consecutive failures, blocks for 60s

**Dead Letter Queue:** Failed tasks after all retries → `failed_tasks` table

**Implementation:** `app/infrastructure/external/bank_simulator.py`, `circuit_breaker.py`

### 5. Scalability

**Horizontal scaling:**
- FastAPI: Stateless, add instances behind load balancer
- Celery: `docker-compose up --scale celery_worker=5`

**Pagination:** Offset-based (simple, works for typical use cases)

**Indexes:**
```sql
-- Optimizes transaction history queries
CREATE INDEX idx_account_status_created ON transactions(account_id, status, created_at DESC);
-- Idempotency lookup
CREATE UNIQUE INDEX idx_unique_idempotency_key ON transactions(idempotency_key)
    WHERE idempotency_key IS NOT NULL;
```

### 6. Security

**Authentication:** JWT tokens (30min expiration), bcrypt password hashing

**Webhook verification:** HMAC signature validation

**Limitations (noted in task):**
- CORS allows all origins (acceptable for assessment)
- No API key rotation

**Implementation:** `app/core/security.py`

## Project Structure

```
app/
├── api/v1/                    # REST endpoints
│   ├── deposits.py            # POST /deposits, GET /deposits/{id}
│   ├── withdrawals.py         # POST /withdrawals, GET /withdrawals/{id}
│   ├── users.py               # GET /users/{id}/balance, /transactions
│   └── auth.py                # POST /auth/login
├── api/middleware/
│   ├── idempotency.py         # Idempotency-Key handling
│   ├── rate_limit.py          # Token bucket rate limiter
│   └── request_id.py          # X-Request-ID correlation
├── domain/services/           # Business logic
│   ├── deposit_service.py
│   └── withdrawal_service.py
├── infrastructure/
│   ├── cache/
│   │   ├── distributed_lock.py # Redis distributed lock
│   │   └── rate_limiter.py
│   ├── external/
│   │   ├── bank_simulator.py   # Simulated bank API (per task)
│   │   └── circuit_breaker.py  # Resilience pattern
│   └── repositories/           # DB access layer
├── workers/
│   ├── celery_app.py
│   └── tasks/                  # Async task processing
│       ├── deposit_tasks.py
│       ├── withdrawal_tasks.py
│       └── webhook_tasks.py
└── admin/                      # Admin panel for monitoring
```

## Testing (70%+ coverage)

**Unit Tests:**
- Distributed lock behavior
- Rate limiter token bucket
- Transaction state machine
- Webhook signature verification

**Integration Tests:**
- Concurrent balance updates (race condition prevention)
- Idempotency enforcement
- Rate limit enforcement
- Bank simulator failures

**Run tests:** `make test`

**Key scenarios tested:**
- 100 concurrent deposits to same account → No race conditions
- Duplicate idempotency keys → Same response returned
- Withdrawal exceeding balance → Rejected
- Bank API failures → Retry with exponential backoff

## Monitoring & Observability

- **Structured logging:** JSON format with correlation IDs (`X-Request-ID`)
- **Flower:** Celery task monitoring at http://localhost:5555
- **Prometheus + Grafana:** Metrics collection (configured but not required per task)

## Known Limitations

1. **Single DB instance** (read replicas not implemented)
2. **Fixed webhook retry** (no exponential backoff for webhooks specifically)
3. **Rate limit clock skew** in distributed setup (acceptable for assessment scale)

## Performance Benchmarks

**Environment:** MacBook Pro M1, 16GB RAM, Docker Desktop

- Deposit creation (100 concurrent): p50=45ms, p95=120ms
- Balance query: p50=8ms
- Transaction processing: 50ms (excluding bank simulator delay)

## Development

**Prerequisites:** Docker 20.10+, Docker Compose 2.0+

**Code quality:**
- Pre-commit hooks: black, isort, ruff, mypy
- Type hints throughout (strict mode)
- Line length: 100 chars

**Makefile commands:**
```bash
make up          # Start services
make down        # Stop services
make migrate     # Run DB migrations
make test        # Run tests
make lint        # Run code quality checks
make logs        # Show logs
## etc. check Makefile for full list
```

## Contact

- **Author:** Necmettin Çolakoğlu
- **Email:** necmettin94@gmail.com | contact@whoisnec.com

---

Built as a technical assessment demonstrating production-grade patterns: async processing, idempotency, rate limiting, distributed locking, error handling, and observability.
