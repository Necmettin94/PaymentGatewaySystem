import time
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.metrics import http_request_duration_seconds, http_requests_total


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)

        endpoint = request.url.path
        for route in request.app.routes:
            match, _ = route.matches(request.scope)
            if match.name == "full":
                endpoint = route.path
                break

        method = request.method

        start_time = time.time()

        try:
            response = await call_next(request)
            status_code = response.status_code

            http_requests_total.labels(
                method=method, endpoint=endpoint, status_code=status_code
            ).inc()

            duration = time.time() - start_time
            http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration)

            return response

        except Exception as exc:
            http_requests_total.labels(method=method, endpoint=endpoint, status_code=500).inc()

            duration = time.time() - start_time
            http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration)

            raise exc
