import hashlib
import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from redis.asyncio import Redis

from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class IdempotencyKeyGenerator:
    @staticmethod
    def generate_auto_key(auth_header: str, request_body: str) -> str:
        hash_input = f"{auth_header}:{request_body}"
        hash_digest = hashlib.sha256(hash_input.encode()).hexdigest()[:32]
        return f"auto-{hash_digest}"


class IdempotencyStatus(str, Enum):
    PROCESSING = "processing"
    COMPLETED = "completed"


class IdempotencyService:
    PROCESSING_LOCK_TTL = 60

    def __init__(self, cache: Redis):
        self.cache = cache
        self.completed_response_ttl = settings.idempotency_key_ttl_hours * 60 * 60

    async def check_existing(self, idempotency_key: str) -> dict[str, Any] | None:
        key = self._get_key(idempotency_key)
        data = await self.cache.get(key)
        if not data:
            return None

        return json.loads(data)

    async def acquire_lock(self, idempotency_key: str) -> bool:
        key = self._get_key(idempotency_key)
        lock_data = {
            "status": IdempotencyStatus.PROCESSING,
            "created_at": datetime.now(UTC).isoformat(),
        }
        success = await self.cache.set(
            key,
            json.dumps(lock_data),
            nx=True,
            ex=self.PROCESSING_LOCK_TTL,
        )

        if success:
            logger.info(
                "idempotency_lock_acquired",
                key=idempotency_key,
                ttl=self.PROCESSING_LOCK_TTL,
            )
        else:
            logger.warning(
                "idempotency_lock_conflict",
                key=idempotency_key,
                reason="Another request is processing",
            )

        return bool(success)

    async def release_lock(self, idempotency_key: str) -> None:
        key = self._get_key(idempotency_key)
        await self.cache.delete(key)

        logger.info(
            "idempotency_lock_released",
            key=idempotency_key,
            reason="Request failed or error occurred",
        )

    async def save_response(
        self,
        idempotency_key: str,
        response_body: bytes,
        status_code: int,
        headers: dict[str, str],
        resource_id: str | None = None,
    ) -> None:
        key = self._get_key(idempotency_key)
        response_data = {
            "status": IdempotencyStatus.COMPLETED,
            "response_body": response_body.decode("utf-8"),
            "status_code": status_code,
            "headers": headers,
            "resource_id": resource_id,
            "created_at": datetime.now(UTC).isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
        }
        await self.cache.set(
            key,
            json.dumps(response_data),
            ex=self.completed_response_ttl,
        )
        logger.info(
            "idempotency_response_cached",
            key=idempotency_key,
            status_code=status_code,
            resource_id=resource_id,
            ttl=self.completed_response_ttl,
        )

    @staticmethod
    def _get_key(idempotency_key: str) -> str:
        return f"idempotency:{idempotency_key}"
