import redis.asyncio as aioredis
from redis.asyncio import Redis

from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class RedisClient:
    _instance: Redis | None = None

    @classmethod
    async def get_instance(cls) -> Redis:
        if cls._instance is None:
            cls._instance = await aioredis.from_url(
                settings.redis_url_str,
                encoding="utf-8",
                decode_responses=True,
            )
            logger.info("redis_connection_established", url=settings.redis_url_str)
        return cls._instance

    @classmethod
    async def close(cls) -> None:
        if cls._instance:
            await cls._instance.aclose()
            cls._instance = None
            logger.info("redis_connection_closed")


# Simplified - removed CachePort abstraction, just using Redis directly
async def get_cache() -> Redis:
    return await RedisClient.get_instance()
