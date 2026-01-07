from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.admin.views import setup_admin
from app.api.middleware.idempotency import IdempotencyMiddleware
from app.api.middleware.rate_limit import RateLimitMiddleware
from app.api.middleware.request_id import RequestIDMiddleware
from app.api.v1 import webhooks
from app.api.v1.router import api_router
from app.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.middleware import PrometheusMiddleware
from app.domain.exceptions import DomainException
from app.infrastructure.cache.redis_client import RedisClient
from app.infrastructure.database.session import engine
from app.schemas.common import ErrorResponse, HealthResponse

configure_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("application_startup", env=settings.app_env)
    await RedisClient.get_instance()
    logger.info("redis_initialized")
    yield

    logger.info("application_shutdown")
    await RedisClient.close()


app = FastAPI(
    title="Payment Gateway API",
    description="Production-grade payment gateway system with async transaction processing",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# SessionMiddleware must be first
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.admin_session_secret,
    max_age=3600,  # 1-hour session
    same_site="lax",  # Allow cookies in redirects
    https_only=False,  # Development mode (use True in production)
    session_cookie="admin_session",  # Explicit cookie name
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # FIXME: need to add env var for allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add custom middleware
app.add_middleware(RequestIDMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(PrometheusMiddleware)

# Setup admin panel AFTER middleware configuration
admin = setup_admin(app, engine)

# frontend
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(api_router)
app.include_router(webhooks.router)


@app.get("/", include_in_schema=False)
async def root():
    from fastapi.responses import FileResponse

    return FileResponse("app/static/index.html")


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    from app.infrastructure.external.bank_simulator import get_circuit_breaker_state

    circuit_state = get_circuit_breaker_state()

    return HealthResponse(
        status="healthy",
        version="1.0.0",
        timestamp=datetime.now(UTC).isoformat(),
        circuit_breaker=circuit_state,
    )


@app.get("/metrics", include_in_schema=False, tags=["System"])
async def metrics():
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.exception_handler(DomainException)
async def domain_exception_handler(request: Request, exc: DomainException):
    logger.warning(
        "domain_exception",
        code=exc.code,
        message=exc.message,
        path=request.url.path,
    )

    status_code_map = {
        "INSUFFICIENT_BALANCE": 400,
        "ACCOUNT_NOT_FOUND": 404,
        "USER_NOT_FOUND": 404,
        "TRANSACTION_NOT_FOUND": 404,
        "DUPLICATE_REQUEST": 409,
        "INVALID_STATE": 400,
        "BANK_ERROR": 502,
        "BANK_UNAVAILABLE": 503,
        "BANK_TIMEOUT": 504,
    }

    status_code = status_code_map.get(exc.code, 500)

    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error=exc.code,
            message=exc.message,
        ).model_dump(),
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    logger.warning(
        "validation_error",
        message=str(exc),
        path=request.url.path,
    )

    return JSONResponse(
        status_code=400,
        content=ErrorResponse(
            error="VALIDATION_ERROR",
            message=str(exc),
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(
        "unexpected_error",
        error=str(exc),
        error_type=type(exc).__name__,
        path=request.url.path,
    )

    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="INTERNAL_SERVER_ERROR",
            message="An unexpected error occurred",
        ).model_dump(),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
