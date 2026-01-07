import pytest

from app.infrastructure.cache.distributed_lock import DistributedLock, distributed_lock


@pytest.mark.asyncio
async def test_lock_acquire_and_release_basic(fake_redis):
    lock = DistributedLock(fake_redis, "test_basic", ttl=10)
    acquired = await lock.acquire()
    assert acquired is True
    exists = await fake_redis.exists("lock:test_basic")
    assert exists == 1
    released = await lock.release()
    assert released is True
    exists = await fake_redis.exists("lock:test_basic")
    assert exists == 0


@pytest.mark.asyncio
async def test_lock_prevents_concurrent_acquisition(fake_redis):
    lock1 = DistributedLock(fake_redis, "test_concurrent", ttl=10)
    lock2 = DistributedLock(fake_redis, "test_concurrent", ttl=10)

    acquired1 = await lock1.acquire()
    assert acquired1 is True

    acquired2 = await lock2.acquire()
    assert acquired2 is False

    await lock1.release()

    acquired2_retry = await lock2.acquire()
    assert acquired2_retry is True

    await lock2.release()


@pytest.mark.asyncio
async def test_lock_context_manager(fake_redis):
    async with distributed_lock(fake_redis, "test_context", ttl=10) as lock:
        assert lock.acquired is True
        exists = await fake_redis.exists("lock:test_context")
        assert exists == 1
    exists = await fake_redis.exists("lock:test_context")
    assert exists == 0


@pytest.mark.asyncio
async def test_concurrent_account_locks_different_accounts(fake_redis):
    from uuid import uuid4

    account1_id = uuid4()
    account2_id = uuid4()

    lock1 = DistributedLock(fake_redis, f"account:{account1_id}", ttl=10)
    lock2 = DistributedLock(fake_redis, f"account:{account2_id}", ttl=10)

    acquired1 = await lock1.acquire()
    acquired2 = await lock2.acquire()

    assert acquired1 is True
    assert acquired2 is True

    exists1 = await fake_redis.exists(f"lock:account:{account1_id}")
    exists2 = await fake_redis.exists(f"lock:account:{account2_id}")

    assert exists1 == 1
    assert exists2 == 1

    await lock1.release()
    await lock2.release()


@pytest.mark.asyncio
async def test_lock_identifier_prevents_wrong_release(fake_redis):
    lock1 = DistributedLock(fake_redis, "test_identifier", ttl=10)
    lock2 = DistributedLock(fake_redis, "test_identifier", ttl=10)
    await lock1.acquire()
    lock2.acquired = True
    released = await lock2.release()
    assert released is False
    exists = await fake_redis.exists("lock:test_identifier")
    assert exists == 1
    released = await lock1.release()
    assert released is True
