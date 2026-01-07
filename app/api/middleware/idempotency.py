import json

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response

from app.core.constants import IDEMPOTENCY_HEADER
from app.core.logging import get_logger
from app.core.services.idempotency_service import IdempotencyService, IdempotencyStatus
from app.infrastructure.cache.redis_client import get_cache

logger = get_logger(__name__)


class IdempotencyMiddleware(BaseHTTPMiddleware):
    IDEMPOTENT_METHODS = {"POST"}
    IDEMPOTENT_PATHS = {"/api/v1/deposits", "/api/v1/withdrawals"}

    def __init__(self, app, cache_getter=None):
        super().__init__(app)
        self._cache_getter = cache_getter or get_cache  # for mocking in tests

    async def dispatch(self, request: Request, call_next):
        if not self._requires_idempotency(request):
            return await call_next(request)

        idempotency_key = request.headers.get(IDEMPOTENCY_HEADER)

        if not idempotency_key:
            logger.warning(
                "missing_idempotency_key",
                path=request.url.path,
                method=request.method,
            )
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Bad Request",
                    "message": f"Missing required header: {IDEMPOTENCY_HEADER}",
                    "details": "Idempotency key is required for this operation to ensure request safety and prevent duplicate processing.",
                },
            )

        request_body = await request.body()

        cache = await self._cache_getter()
        service = IdempotencyService(cache)

        lock_acquired = await service.acquire_lock(idempotency_key)

        if not lock_acquired:

            existing = await service.check_existing(idempotency_key)

            if existing:
                status = existing.get("status")

                if status == IdempotencyStatus.COMPLETED:
                    logger.info(
                        "idempotency_cache_hit",
                        key=idempotency_key,
                        resource_id=existing.get("resource_id"),
                        cached_status_code=existing.get("status_code"),
                    )

                    cached_headers = existing.get("headers", {})
                    cached_headers[IDEMPOTENCY_HEADER] = idempotency_key

                    return Response(
                        content=existing["response_body"].encode("utf-8"),
                        status_code=existing["status_code"],
                        media_type="application/json",
                        headers=cached_headers,
                    )

            logger.warning(
                "idempotency_race_condition",
                key=idempotency_key,
                reason="Lock acquired by another request during check",
            )
            return JSONResponse(
                status_code=409,
                content={
                    "error": "conflict",
                    "message": "this request is already being processed. please retry in a few seconds.",
                    "idempotency_key": idempotency_key,
                },
                headers={
                    "Retry-After": "5",
                    IDEMPOTENCY_HEADER: idempotency_key,
                },
            )

        try:
            body_sent = False

            async def receive():
                nonlocal body_sent  # local variable to track if body has been sent
                if not body_sent:
                    body_sent = True
                    return {"type": "http.request", "body": request_body}
                else:
                    return {"type": "http.disconnect"}

            scope = request.scope

            response: Response = await call_next(StarletteRequest(scope, receive))

            response_body = b""
            async for chunk in response.body_iterator:
                response_body += chunk

            if response.status_code < 400:
                resource_id = None
                try:
                    response_json = json.loads(response_body)
                    resource_id = response_json.get("id")
                    if resource_id:
                        resource_id = str(resource_id)
                except Exception:
                    pass  # nosec

                await service.save_response(
                    idempotency_key=idempotency_key,
                    response_body=response_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    resource_id=resource_id,
                )

                logger.info(
                    "idempotency_request_completed",
                    key=idempotency_key,
                    status_code=response.status_code,
                    resource_id=resource_id,
                )
            else:
                await service.release_lock(idempotency_key)

                logger.warning(
                    "idempotency_request_failed",
                    key=idempotency_key,
                    status_code=response.status_code,
                    reason="Non-success status code, lock released for retry",
                )

            return Response(
                content=response_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        except Exception as e:
            await service.release_lock(idempotency_key)

            logger.error(
                "idempotency_request_exception",
                key=idempotency_key,
                error=str(e),
                error_type=type(e).__name__,
            )

            raise

    def _requires_idempotency(self, request: Request) -> bool:
        if request.method not in self.IDEMPOTENT_METHODS:
            return False

        for path in self.IDEMPOTENT_PATHS:
            if path in request.url.path:
                return True

        return False
