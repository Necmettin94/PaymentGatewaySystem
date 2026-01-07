from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.middleware.rate_limit_config import RateLimitConfig
from app.config import settings
from app.core.constants import (
    RATE_LIMIT_HEADER,
    RATE_LIMIT_REMAINING_HEADER,
    RATE_LIMIT_RESET_HEADER,
)
from app.core.logging import get_logger
from app.infrastructure.cache.rate_limiter import RateLimiter
from app.infrastructure.cache.redis_client import RedisClient

logger = get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.rate_limiter: RateLimiter | None = None

    async def dispatch(self, request: Request, call_next):
        if not settings.rate_limit_enabled:
            return await call_next(request)

        if self.rate_limiter is None:
            redis_client = await RedisClient.get_instance()
            self.rate_limiter = RateLimiter(redis_client)

        rule = RateLimitConfig.get_rule_for_request(request.url.path, request.method)
        if rule is None:
            return await call_next(request)

        limit = rule.get_limit()
        window = rule.window_seconds

        key = self._build_rate_limit_key(request, rule.pattern)
        is_allowed, remaining, reset_timestamp = await self.rate_limiter.is_allowed(
            key=key,
            limit=limit,
            window_seconds=window,
        )
        headers = {
            RATE_LIMIT_HEADER: str(limit),
            RATE_LIMIT_REMAINING_HEADER: str(remaining),
            RATE_LIMIT_RESET_HEADER: str(reset_timestamp),
        }

        if not is_allowed:
            logger.warning(
                "rate_limit_exceeded",
                key=key,
                limit=limit,
                path=request.url.path,
                method=request.method,
                endpoint=rule.description,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit exceeded for {rule.description}. Please try again later.",
                    "retry_after": window,
                    "limit": limit,
                    "window_seconds": window,
                },
                headers=headers,
            )
        response: Response = await call_next(request)
        for header_name, header_value in headers.items():
            response.headers[header_name] = header_value

        return response

    @staticmethod
    def _build_rate_limit_key(request: Request, pattern: str) -> str:
        user_id = getattr(request.state, "user_id", None)

        if user_id:
            return f"rate_limit:user:{user_id}:{pattern}"
        else:
            client_ip = request.client.host if request.client else "test_client"
            return f"rate_limit:ip:{client_ip}:{pattern}"
