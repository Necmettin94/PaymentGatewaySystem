import time

from redis.asyncio import Redis

from app.core.logging import get_logger

logger = get_logger(__name__)


class RateLimiter:
    def __init__(self, redis_client: Redis):
        self.redis = redis_client

    async def is_allowed(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> tuple[bool, int, int]:
        now = time.time()
        window_start = now - window_seconds

        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, window_seconds)
        _, current_count, _, _ = await pipe.execute()

        is_allowed = current_count < limit
        remaining = max(0, limit - current_count - 1) if is_allowed else 0
        reset_timestamp = int(now + window_seconds)

        if not is_allowed:
            logger.warning(
                "rate_limit_exceeded",
                key=key,
                limit=limit,
                current_count=current_count,
            )

        return is_allowed, remaining, reset_timestamp

    async def reset(self, key: str) -> None:
        await self.redis.delete(key)
        logger.info("rate_limit_reset", key=key)
