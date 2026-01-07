import asyncio
from unittest.mock import AsyncMock

import pytest

from app.infrastructure.cache.distributed_lock import DistributedLock, LockAcquisitionError


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    return redis


@pytest.mark.asyncio
async def test_lock_acquire_success(mock_redis):
    mock_redis.set = AsyncMock(return_value=True)

    lock = DistributedLock(mock_redis, "test_key", ttl=10)
    result = await lock.acquire()

    assert result is True
    assert lock.acquired is True
    mock_redis.set.assert_called_once()


@pytest.mark.asyncio
async def test_lock_acquire_failure(mock_redis):
    mock_redis.set = AsyncMock(return_value=False)

    lock = DistributedLock(mock_redis, "test_key", ttl=10)
    result = await lock.acquire()

    assert result is False
    assert lock.acquired is False


@pytest.mark.asyncio
async def test_lock_release_success(mock_redis):
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.eval = AsyncMock(return_value=1)

    lock = DistributedLock(mock_redis, "test_key", ttl=10)
    await lock.acquire()
    result = await lock.release()

    assert result is True
    assert lock.acquired is False
    assert mock_redis.eval.called


@pytest.mark.asyncio
async def test_lock_release_without_acquire(mock_redis):
    lock = DistributedLock(mock_redis, "test_key", ttl=10)
    result = await lock.release()

    assert result is False
    assert not mock_redis.eval.called


@pytest.mark.asyncio
async def test_lock_blocking_mode_timeout(mock_redis):
    mock_redis.set = AsyncMock(return_value=False)

    lock = DistributedLock(
        mock_redis,
        "test_key",
        ttl=10,
        blocking=True,
        retry_timeout=0.2,
        retry_delay=0.05,
    )

    with pytest.raises(LockAcquisitionError) as exc_info:
        await lock.acquire()

    assert "Failed to acquire lock" in str(exc_info.value)
    assert lock.acquired is False


@pytest.mark.asyncio
async def test_lock_extend_success(mock_redis):
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.eval = AsyncMock(return_value=1)

    lock = DistributedLock(mock_redis, "test_key", ttl=10)
    await lock.acquire()

    result = await lock.extend(additional_ttl=10)

    assert result is True
    assert mock_redis.eval.called


@pytest.mark.asyncio
async def test_lock_extend_without_acquire(mock_redis):
    lock = DistributedLock(mock_redis, "test_key", ttl=10)
    result = await lock.extend(additional_ttl=10)

    assert result is False
    assert not mock_redis.eval.called


@pytest.mark.asyncio
async def test_lock_context_manager_success(mock_redis):
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.eval = AsyncMock(return_value=1)

    async with DistributedLock(mock_redis, "test_key", ttl=10) as lock:
        assert lock.acquired is True

    assert mock_redis.eval.called


@pytest.mark.asyncio
async def test_lock_context_manager_with_exception(mock_redis):
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.eval = AsyncMock(return_value=1)

    with pytest.raises(ValueError):
        async with DistributedLock(mock_redis, "test_key", ttl=10) as lock:
            assert lock.acquired is True
            raise ValueError("Test exception")

    assert mock_redis.eval.called


@pytest.mark.asyncio
async def test_lock_ttl_capped_at_30_seconds(mock_redis):
    mock_redis.set = AsyncMock(return_value=True)

    lock = DistributedLock(mock_redis, "test_key", ttl=60)
    await lock.acquire()

    assert lock.ttl == 30
    mock_redis.set.assert_called_once()


@pytest.mark.asyncio
async def test_lock_unique_identifiers():
    lock1 = DistributedLock(AsyncMock(), "test_key", ttl=10)
    lock2 = DistributedLock(AsyncMock(), "test_key", ttl=10)

    assert lock1.lock_identifier != lock2.lock_identifier


@pytest.mark.asyncio
async def test_lock_key_prefix():
    lock = DistributedLock(AsyncMock(), "account:123", ttl=10)

    assert lock.key == "lock:account:123"


@pytest.mark.asyncio
async def test_blocking_mode_exponential_backoff(mock_redis):
    call_count = 0

    async def mock_set(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return call_count > 3

    mock_redis.set = mock_set

    lock = DistributedLock(
        mock_redis,
        "test_key",
        ttl=10,
        blocking=True,
        retry_timeout=10,
        retry_delay=0.05,
    )

    start = asyncio.get_event_loop().time()
    await lock.acquire()
    elapsed = asyncio.get_event_loop().time() - start

    assert call_count >= 4
    assert elapsed >= 0.05
