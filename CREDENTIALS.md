# Payment Gateway - Test Credentials & Scenarios

This document contains all necessary information for testing the payment gateway system.

## Quick Start Testing

### Step 1: Start the System

```bash
# Clone and navigate to project
git clone <repository-url>
cd PaymentGatewaySystem

# Copy environment file
cp .env.example .env

# Start all services
make up

# Run migrations
make migrate

# Wait for services to be healthy (30 seconds)
```

### Step 2: Verify Services Are Running

```bash
# Check health endpoint
curl http://localhost:8000/health

# Expected response:
{
  "status": "healthy",
  "version": "1.0.0"
}
```

## Test User Accounts

The system requires creating user accounts through the registration endpoint. No pre-seeded users exist.

### Create Test User

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "full_name": "Test User",
    "password": "password123"
  }'
```

**Expected Response:**
```json
{
  "id": "uuid",
  "email": "test@example.com",
  "full_name": "Test User",
  "is_active": true,
  "account": {
    "id": "uuid",
    "balance": "0.00",
    "currency": "USD"
  },
  "created_at": "2026-01-05T23:00:00.000000"
}
```

### Login

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123"
  }'
```

**Expected Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Save the token for subsequent requests:**
```bash
export TOKEN="your-access-token-here"
```

## Test Scenarios

### Scenario 1: Basic Deposit Flow

**Objective:** Create a deposit and verify balance update after bank processing.

**Steps:**

1. Create deposit request:
```bash
curl -X POST http://localhost:8000/api/v1/deposits \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: test-deposit-001" \
  -d '{
    "amount": 100.00,
    "currency": "USD"
  }'
```

**Expected Response (202 Accepted):**
```json
{
  "id": "transaction-uuid",
  "account_id": "account-uuid",
  "transaction_type": "DEPOSIT",
  "amount": "100.00",
  "currency": "USD",
  "status": "PENDING",
  "created_at": "2026-01-05T23:00:00.000000"
}
```

2. Wait 2-10 seconds for bank processing (simulated)

3. Check transaction status:
```bash
curl -X GET http://localhost:8000/api/v1/deposits/{transaction-id} \
  -H "Authorization: Bearer $TOKEN"
```

**Expected Response (after processing):**
```json
{
  "id": "transaction-uuid",
  "status": "SUCCESS",
  "amount": "100.00",
  "bank_transaction_id": "BANK-12345",
  "updated_at": "2026-01-05T23:00:10.000000"
}
```

4. Verify balance:
```bash
curl -X GET http://localhost:8000/api/v1/users/me/balance \
  -H "Authorization: Bearer $TOKEN"
```

**Expected Response:**
```json
{
  "balance": "100.00",
  "currency": "USD"
}
```

**Success Criteria:**
- Deposit created with PENDING status
- After 2-10 seconds, status becomes SUCCESS
- Balance increases by deposit amount

### Scenario 2: Basic Withdrawal Flow

**Prerequisite:** Complete Scenario 1 to have balance.

**Steps:**

1. Create withdrawal request:
```bash
curl -X POST http://localhost:8000/api/v1/withdrawals \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: test-withdrawal-001" \
  -d '{
    "amount": 50.00,
    "currency": "USD"
  }'
```

**Expected Response (202 Accepted):**
```json
{
  "id": "transaction-uuid",
  "status": "PENDING",
  "amount": "50.00"
}
```

2. Wait 2-10 seconds for processing

3. Check balance after SUCCESS:
```bash
curl -X GET http://localhost:8000/api/v1/users/me/balance \
  -H "Authorization: Bearer $TOKEN"
```

**Expected Balance:**
```json
{
  "balance": "50.00"
}
```

**Success Criteria:**
- Withdrawal created with PENDING status
- Balance remains 100.00 during PENDING (not deducted yet)
- After SUCCESS, balance becomes 50.00

### Scenario 3: Insufficient Balance

**Objective:** Verify withdrawal fails when balance is insufficient.

**Steps:**

1. Attempt to withdraw more than available balance:
```bash
curl -X POST http://localhost:8000/api/v1/withdrawals \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: test-withdrawal-insufficient" \
  -d '{
    "amount": 5000.00,
    "currency": "USD"
  }'
```

**Expected Response (400 Bad Request):**
```json
{
  "detail": "Insufficient balance. Available: 50.00, Required: 5000.00"
}
```

**Success Criteria:**
- Request rejected immediately
- Balance unchanged
- Clear error message

### Scenario 4: Idempotency Test

**Objective:** Verify duplicate requests with same idempotency key return same result.

**Steps:**

1. Create deposit with specific idempotency key:
```bash
curl -X POST http://localhost:8000/api/v1/deposits \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: idempotency-test-123" \
  -d '{
    "amount": 25.00,
    "currency": "USD"
  }'
```

**Note the transaction ID from response.**

2. Send exact same request again (within 24 hours):
```bash
curl -X POST http://localhost:8000/api/v1/deposits \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: idempotency-test-123" \
  -d '{
    "amount": 25.00,
    "currency": "USD"
  }'
```

**Expected Response:**
- Same transaction ID as first request
- Same status (PENDING or SUCCESS depending on timing)
- No new transaction created
- Balance only updated once

**Success Criteria:**
- Second request returns cached response
- Only one transaction exists with that idempotency key
- Balance not double-counted

### Scenario 5: Rate Limiting Test

**Objective:** Verify rate limiting enforces request limits.

**Steps:**

1. Make 11 rapid balance requests (limit is 10/minute):
```bash
for i in {1..11}; do
  curl -X GET http://localhost:8000/api/v1/users/me/balance \
    -H "Authorization: Bearer $TOKEN" \
    -i
done
```

**Expected Responses:**
- First 10 requests: 200 OK with balance
- 11th request: 429 Too Many Requests

**Headers from 10th request:**
```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1704495600
```

**11th request response:**
```json
{
  "detail": "Rate limit exceeded. Try again in 60 seconds.",
  "retry_after": 60
}
```

**Success Criteria:**
- Rate limit enforced correctly
- Appropriate headers provided
- Clear error message with retry guidance

### Scenario 6: Transaction History

**Objective:** List all transactions for a user.

**Steps:**

1. Get transaction history:
```bash
curl -X GET "http://localhost:8000/api/v1/users/me/transactions?skip=0&limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

**Expected Response:**
```json
{
  "items": [
    {
      "id": "uuid",
      "transaction_type": "DEPOSIT",
      "amount": "100.00",
      "status": "SUCCESS",
      "created_at": "2026-01-05T23:00:00.000000"
    },
    {
      "id": "uuid",
      "transaction_type": "WITHDRAWAL",
      "amount": "50.00",
      "status": "SUCCESS",
      "created_at": "2026-01-05T23:05:00.000000"
    }
  ],
  "total": 2,
  "skip": 0,
  "limit": 10
}
```

**Success Criteria:**
- All user transactions listed
- Sorted by creation date (newest first)
- Pagination works correctly

### Scenario 7: Bank Processing Failure

**Objective:** Verify system handles bank failures gracefully.

**Note:** Bank simulator has 90% success rate, so some transactions will fail naturally.

**Steps:**

1. Create multiple deposits until one fails:
```bash
for i in {1..10}; do
  curl -X POST http://localhost:8000/api/v1/deposits \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: test-failure-$i" \
    -d '{"amount": 10.00, "currency": "USD"}'
  sleep 1
done
```

2. Check for failed transactions:
```bash
curl -X GET "http://localhost:8000/api/v1/deposits?status=FAILED" \
  -H "Authorization: Bearer $TOKEN"
```

**Expected Failed Transaction:**
```json
{
  "id": "uuid",
  "status": "FAILED",
  "error_code": "BANK_ERROR",
  "error_message": "Bank processing failed",
  "amount": "10.00"
}
```

**Success Criteria:**
- Failed transactions marked as FAILED
- Error details captured
- Balance not updated for failed deposits
- Failed withdrawals don't deduct balance

### Scenario 8: Concurrent Operations

**Objective:** Verify system handles concurrent requests safely.

**Steps:**

1. Create test script for concurrent deposits:
```bash
#!/bin/bash
for i in {1..5}; do
  (curl -X POST http://localhost:8000/api/v1/deposits \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: concurrent-$i" \
    -d '{"amount": 20.00, "currency": "USD"}' &)
done
wait
```

2. Verify all transactions processed correctly:
```bash
curl -X GET http://localhost:8000/api/v1/users/me/transactions \
  -H "Authorization: Bearer $TOKEN"
```

**Success Criteria:**
- All 5 deposits created
- No duplicate transactions
- Balance correct (sum of all successful deposits)
- No race conditions

## Admin Panel Access

**URL:** http://localhost:8000/admin

**Credentials:** Use any registered user's email and password

**Features:**
- View all transactions
- Filter by status, type, user
- Search by transaction ID
- View transaction details
- Monitor system health

## Flower Dashboard

**URL:** http://localhost:5555

**Authentication:** No authentication required in development

**Features:**
- Monitor Celery workers
- View task queue depth
- Track task success/failure rates
- Inspect task details
- View worker performance

## RabbitMQ Management

**URL:** http://localhost:15672

**Credentials:**
- Username: guest
- Password: guest

**Features:**
- Monitor message queue depth
- View exchange bindings
- Track message rates
- Inspect queue properties

## API Documentation

**Swagger UI:** http://localhost:8000/docs

**ReDoc:** http://localhost:8000/redoc

**Features:**
- Interactive API testing
- Request/response schemas
- Authentication flow
- Example requests

## Environment Configuration

All environment variables are in `.env` file. Key variables for testing:

```bash
# Bank Simulator Settings
BANK_SIMULATOR_SUCCESS_RATE=0.9    # 90% success rate
BANK_SIMULATOR_MIN_DELAY=2         # Minimum processing time (seconds)
BANK_SIMULATOR_MAX_DELAY=10        # Maximum processing time (seconds)

# Rate Limiting
RATE_LIMIT_PER_USER_BALANCE=10     # Balance queries per minute
RATE_LIMIT_PER_USER_TRANSACTIONS=20 # Transaction list per minute
RATE_LIMIT_GLOBAL=1000             # Total API requests per minute

# Idempotency
IDEMPOTENCY_KEY_TTL_HOURS=24       # How long keys are cached

# JWT
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30  # Token expiration
```

## Expected Test Results

After running all scenarios, expected state:

**User Balance:**
- Initial: 0.00
- After Scenario 1 (deposit 100): 100.00
- After Scenario 2 (withdraw 50): 50.00
- After Scenario 4 (deposit 25): 75.00
- After Scenario 7 (10 deposits, ~9 succeed): ~165.00
- After Scenario 8 (5 deposits of 20): ~265.00

**Note:** Exact balance depends on bank simulator success rate (90%).

**Transaction Count:**
- Total created: 20+
- Successful: ~18 (90% success rate)
- Failed: ~2 (10% failure rate)
- Pending: 0 (all should complete within 10 seconds)

## Troubleshooting Testing Issues

### Token Expired

**Symptom:** 401 Unauthorized errors

**Solution:**
```bash
# Login again to get new token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "password123"}'

# Update TOKEN variable
export TOKEN="new-access-token"
```

### Transaction Stuck in PENDING

**Symptom:** Transaction never completes

**Solution:**
```bash
# Check Celery worker logs
docker-compose logs worker

# Check if worker is running
docker-compose ps worker

# Restart worker if needed
docker-compose restart worker
```

### Rate Limit Not Resetting

**Symptom:** Still rate limited after waiting

**Solution:**
```bash
# Wait full 60 seconds
# Or flush Redis
docker-compose exec redis redis-cli FLUSHDB
```

### Balance Mismatch

**Symptom:** Balance doesn't match expected value

**Solution:**
```bash
# Check all transactions
curl -X GET http://localhost:8000/api/v1/users/me/transactions \
  -H "Authorization: Bearer $TOKEN"

# Sum all successful deposits minus successful withdrawals
# Account for ~10% failure rate in bank simulator
```

## Complete Test Workflow

Run this complete workflow to verify all functionality:

```bash
#!/bin/bash
set -e

echo "1. Register user..."
REGISTER_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "workflow@example.com", "full_name": "Workflow Test", "password": "password123"}')
USER_ID=$(echo $REGISTER_RESPONSE | jq -r '.id')
echo "User ID: $USER_ID"

echo "2. Login..."
LOGIN_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "workflow@example.com", "password": "password123"}')
TOKEN=$(echo $LOGIN_RESPONSE | jq -r '.access_token')
echo "Token obtained"

echo "3. Create deposit..."
DEPOSIT_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/deposits \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: workflow-deposit-1" \
  -d '{"amount": 100.00, "currency": "USD"}')
DEPOSIT_ID=$(echo $DEPOSIT_RESPONSE | jq -r '.id')
echo "Deposit ID: $DEPOSIT_ID"

echo "4. Wait for processing (10 seconds)..."
sleep 10

echo "5. Check deposit status..."
curl -s -X GET http://localhost:8000/api/v1/deposits/$DEPOSIT_ID \
  -H "Authorization: Bearer $TOKEN" | jq

echo "6. Check balance..."
curl -s -X GET http://localhost:8000/api/v1/users/me/balance \
  -H "Authorization: Bearer $TOKEN" | jq

echo "7. Create withdrawal..."
WITHDRAWAL_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/withdrawals \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: workflow-withdrawal-1" \
  -d '{"amount": 30.00, "currency": "USD"}')
WITHDRAWAL_ID=$(echo $WITHDRAWAL_RESPONSE | jq -r '.id')
echo "Withdrawal ID: $WITHDRAWAL_ID"

echo "8. Wait for processing (10 seconds)..."
sleep 10

echo "9. Check final balance..."
curl -s -X GET http://localhost:8000/api/v1/users/me/balance \
  -H "Authorization: Bearer $TOKEN" | jq

echo "10. Get transaction history..."
curl -s -X GET http://localhost:8000/api/v1/users/me/transactions \
  -H "Authorization: Bearer $TOKEN" | jq

echo "Test workflow complete!"
```

Save as `test_workflow.sh`, make executable with `chmod +x test_workflow.sh`, and run with `./test_workflow.sh`.

## Support

If you encounter issues during testing:

1. Check service health: `curl http://localhost:8000/health`
2. Review logs: `docker-compose logs -f`
3. Verify services: `docker-compose ps`
4. Restart if needed: `docker-compose restart`
5. Check documentation: http://localhost:8000/docs

---

**Last Updated:** January 2026
**Testing Status:** All scenarios verified
**Expected Success Rate:** ~90% (due to bank simulator)
