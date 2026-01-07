import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.infrastructure.cache.rate_limiter import RateLimiter


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.pipeline = MagicMock()
    pipeline = AsyncMock()
    pipeline.zremrangebyscore = MagicMock(return_value=pipeline)
    pipeline.zcard = MagicMock(return_value=pipeline)
    pipeline.zadd = MagicMock(return_value=pipeline)
    pipeline.expire = MagicMock(return_value=pipeline)
    pipeline.execute = AsyncMock()

    redis.pipeline.return_value = pipeline

    return redis


@pytest.fixture
def rate_limiter(mock_redis):
    return RateLimiter(mock_redis)


@pytest.mark.asyncio
async def test_rate_limiter_allows_first_request(rate_limiter, mock_redis):
    pipeline = mock_redis.pipeline.return_value
    pipeline.execute.return_value = [None, 0, None, None]

    is_allowed, remaining, reset_time = await rate_limiter.is_allowed(
        key="test_key", limit=10, window_seconds=60
    )

    assert is_allowed is True
    assert remaining == 9  # 10 - 0 - 1
    assert reset_time > time.time()


@pytest.mark.asyncio
async def test_rate_limiter_blocks_when_limit_exceeded(rate_limiter, mock_redis):
    pipeline = mock_redis.pipeline.return_value
    pipeline.execute.return_value = [None, 10, None, None]

    is_allowed, remaining, reset_time = await rate_limiter.is_allowed(
        key="test_key", limit=10, window_seconds=60
    )

    assert is_allowed is False
    assert remaining == 0
    assert reset_time > time.time()


@pytest.mark.asyncio
async def test_rate_limiter_remaining_count(rate_limiter, mock_redis):
    pipeline = mock_redis.pipeline.return_value
    pipeline.execute.return_value = [None, 5, None, None]

    is_allowed, remaining, reset_time = await rate_limiter.is_allowed(
        key="test_key", limit=10, window_seconds=60
    )

    assert is_allowed is True
    assert remaining == 4  # 10 - 5 - 1


@pytest.mark.asyncio
async def test_rate_limiter_redis_pipeline_operations(rate_limiter, mock_redis):
    pipeline = mock_redis.pipeline.return_value
    pipeline.execute.return_value = [None, 5, None, None]

    key = "test_key"
    limit = 10
    window = 60

    await rate_limiter.is_allowed(key=key, limit=limit, window_seconds=window)

    pipeline.zremrangebyscore.assert_called_once()
    pipeline.zcard.assert_called_once()
    pipeline.zadd.assert_called_once()
    pipeline.expire.assert_called_once_with(key, window)
    pipeline.execute.assert_called_once()


@pytest.mark.asyncio
async def test_rate_limiter_reset(rate_limiter, mock_redis):

    key = "test_key"

    await rate_limiter.reset(key)

    mock_redis.delete.assert_called_once_with(key)


@pytest.mark.asyncio
async def test_rate_limiter_window_calculation(rate_limiter, mock_redis):

    pipeline = mock_redis.pipeline.return_value
    pipeline.execute.return_value = [None, 0, None, None]

    window_seconds = 60
    before_time = time.time()

    await rate_limiter.is_allowed(key="test_key", limit=10, window_seconds=window_seconds)

    after_time = time.time()

    call_args = pipeline.zremrangebyscore.call_args[0]
    key_arg = call_args[0]
    min_score = call_args[1]
    max_score = call_args[2]

    assert key_arg == "test_key"
    assert min_score == 0

    assert before_time - window_seconds - 1 <= max_score <= after_time - window_seconds + 1


@pytest.mark.asyncio
async def test_rate_limiter_reset_timestamp(rate_limiter, mock_redis):
    pipeline = mock_redis.pipeline.return_value
    pipeline.execute.return_value = [None, 5, None, None]

    window_seconds = 60
    before_time = time.time()

    _, _, reset_time = await rate_limiter.is_allowed(
        key="test_key", limit=10, window_seconds=window_seconds
    )

    after_time = time.time()

    assert int(before_time + window_seconds) <= reset_time <= int(after_time + window_seconds) + 1


@pytest.mark.asyncio
async def test_rate_limiter_edge_case_zero_limit(rate_limiter, mock_redis):
    pipeline = mock_redis.pipeline.return_value
    pipeline.execute.return_value = [None, 0, None, None]

    is_allowed, remaining, _ = await rate_limiter.is_allowed(
        key="test_key", limit=0, window_seconds=60
    )

    assert is_allowed is False
    assert remaining == 0


@pytest.mark.asyncio
async def test_rate_limiter_edge_case_one_limit(rate_limiter, mock_redis):
    pipeline = mock_redis.pipeline.return_value

    pipeline.execute.return_value = [None, 0, None, None]
    is_allowed, remaining, _ = await rate_limiter.is_allowed(
        key="test_key", limit=1, window_seconds=60
    )
    assert is_allowed is True
    assert remaining == 0

    pipeline.execute.return_value = [None, 1, None, None]
    is_allowed, remaining, _ = await rate_limiter.is_allowed(
        key="test_key", limit=1, window_seconds=60
    )
    assert is_allowed is False
    assert remaining == 0


@pytest.mark.asyncio
async def test_rate_limiter_large_limit(rate_limiter, mock_redis):
    pipeline = mock_redis.pipeline.return_value
    pipeline.execute.return_value = [None, 500, None, None]

    limit = 1000
    is_allowed, remaining, _ = await rate_limiter.is_allowed(
        key="test_key", limit=limit, window_seconds=60
    )

    assert is_allowed is True
    assert remaining == 499  # 1000 - 500 - 1
