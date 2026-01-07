import asyncio
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import uuid4

from redis.asyncio import Redis

from app.core.logging import get_logger

logger = get_logger(__name__)


class LockAcquisitionError(Exception):
    pass


class DistributedLock:
    def __init__(
        self,
        redis: Redis,
        key: str,
        ttl: int = 10,
        blocking: bool = False,
        retry_timeout: int = 30,
        retry_delay: float = 0.1,
    ):
        self.redis = redis
        self.key = f"lock:{key}"
        self.ttl = min(ttl, 30)
        self.blocking = blocking
        self.retry_timeout = retry_timeout
        self.retry_delay = retry_delay
        self.lock_identifier = str(uuid4())
        self.acquired = False

    async def acquire(self) -> bool:
        if self.blocking:
            return await self._acquire_with_retry()
        else:
            return await self._try_acquire_once()

    async def _try_acquire_once(self) -> bool:
        result = await self.redis.set(
            self.key,
            self.lock_identifier,
            nx=True,  # setnx
            ex=self.ttl,  # expire
        )
        self.acquired = bool(result) if result is not None else False

        if self.acquired:
            logger.info(
                "distributed_lock_acquired",
                key=self.key,
                ttl=self.ttl,
                lock_id=self.lock_identifier[:8],
            )
        else:
            logger.debug(
                "distributed_lock_failed",
                key=self.key,
                reason="Lock already held by another process",
            )

        return bool(self.acquired)

    async def _acquire_with_retry(self) -> bool:
        start_time = time.monotonic()
        delay = self.retry_delay
        attempt = 0

        while time.monotonic() - start_time < self.retry_timeout:
            attempt += 1
            if await self._try_acquire_once():
                logger.info(
                    "distributed_lock_acquired_after_retry",
                    key=self.key,
                    attempts=attempt,
                    elapsed_ms=int((time.monotonic() - start_time) * 1000),
                )
                return True
            await asyncio.sleep(delay)
            delay = min(delay * 2, 1.0)  # Cap at 1 second

        elapsed = time.monotonic() - start_time
        logger.warning(
            "distributed_lock_timeout",
            key=self.key,
            attempts=attempt,
            timeout=self.retry_timeout,
            elapsed=elapsed,
        )
        raise LockAcquisitionError(
            f"Failed to acquire lock '{self.key}' after {attempt} attempts ({elapsed:.2f}s)"
        )

    async def release(self) -> bool:
        if not self.acquired:
            logger.debug(
                "distributed_lock_release_skipped", key=self.key, reason="Lock not acquired"
            )
            return False

        # lua script for atomic check-and-delete to release the lock
        # only delete if the lock identifier matches (prevents releasing other process's lock)
        lua_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("DEL", KEYS[1])
        else
            return 0
        end
        """

        released = await self.redis.eval(lua_script, 1, self.key, self.lock_identifier)

        if released:
            logger.info(
                "distributed_lock_released",
                key=self.key,
                lock_id=self.lock_identifier[:8],
            )
            self.acquired = False
            return True
        else:
            logger.warning(
                "distributed_lock_release_failed",
                key=self.key,
                lock_id=self.lock_identifier[:8],
                reason="Lock expired or already released",
            )
            self.acquired = False
            return False

    async def extend(self, additional_ttl: int = 10) -> bool:
        if not self.acquired:
            return False

        lua_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("EXPIRE", KEYS[1], ARGV[2])
        else
            return 0
        end
        """

        extended = await self.redis.eval(
            lua_script, 1, self.key, self.lock_identifier, additional_ttl
        )

        if extended:
            logger.info(
                "distributed_lock_extended",
                key=self.key,
                additional_ttl=additional_ttl,
            )
            return True
        else:
            logger.warning(
                "distributed_lock_extend_failed",
                key=self.key,
                reason="Lock expired or identifier mismatch",
            )
            return False

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release()
        return False  # Don't suppress exceptions


@asynccontextmanager
async def distributed_lock(
    redis: Redis,
    key: str,
    ttl: int = 10,
    blocking: bool = False,
    retry_timeout: int = 30,
) -> AsyncGenerator[DistributedLock, None]:
    lock = DistributedLock(
        redis=redis,
        key=key,
        ttl=ttl,
        blocking=blocking,
        retry_timeout=retry_timeout,
    )

    try:
        await lock.acquire()
        yield lock
    finally:
        await lock.release()


# Synchronous version for use in non-async contexts (tests, Celery tasks)
class SyncDistributedLock:
    def __init__(
        self,
        redis,
        key: str,
        ttl: int = 10,
        blocking: bool = False,
        retry_timeout: int = 30,
    ):
        self.redis = redis
        self.key = f"lock:{key}"
        self.ttl = min(ttl, 30)
        self.blocking = blocking
        self.retry_timeout = retry_timeout
        self.lock_identifier = str(uuid4())
        self.acquired = False

    def acquire(self) -> bool:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                self.acquired = loop.run_until_complete(self._try_acquire_once())
            finally:
                loop.close()

            if self.acquired:
                logger.info(
                    "sync_distributed_lock_acquired",
                    key=self.key,
                    ttl=self.ttl,
                    lock_id=self.lock_identifier[:8],
                )
            return self.acquired
        except Exception as e:
            logger.error(
                "sync_distributed_lock_acquire_failed",
                key=self.key,
                error=str(e),
            )
            self.acquired = False
            return False

    async def _try_acquire_once(self) -> bool:
        acquired = await self.redis.set(
            self.key,
            self.lock_identifier,
            nx=True,
            ex=self.ttl,
        )
        return bool(acquired)

    def release(self) -> bool:
        if not self.acquired:
            return False

        async def _release():
            lua_script = """
            if redis.call("GET", KEYS[1]) == ARGV[1] then
                return redis.call("DEL", KEYS[1])
            else
                return 0
            end
            """
            _released = await self.redis.eval(lua_script, 1, self.key, self.lock_identifier)
            return bool(_released)

        try:
            released = asyncio.run(_release())
            if released:
                logger.info("sync_distributed_lock_released", key=self.key)
            self.acquired = False
            return released
        except RuntimeError:
            loop = asyncio.get_event_loop()
            future = asyncio.run_coroutine_threadsafe(_release(), loop)
            released = future.result()
            self.acquired = False
            return released

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False
