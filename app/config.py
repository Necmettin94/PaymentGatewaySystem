from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = True
    log_level: str = "INFO"

    database_url: PostgresDsn = Field(
        default="postgresql+psycopg2://payment_user:payment_pass@localhost:5432/payment_gateway"
    )

    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")

    celery_broker_url: str = Field(default="amqp://rabbitmq_user:rabbitmq_pass@localhost:5672//")
    celery_result_backend: str = Field(default="redis://localhost:6379/1")
    celery_task_always_eager: bool = False
    celery_task_max_retries: int = 3
    celery_task_retry_backoff: bool = True
    celery_task_retry_backoff_max: int = 600

    jwt_secret_key: str = Field(default="your-secret-key-change-this-in-production")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30

    bank_webhook_secret: str = Field(default="your-bank-webhook-secret-change-this")

    admin_emails: list[str] = Field(
        default=["admin@example.com"], description="Email addresses allowed to access admin panel"
    )
    admin_session_secret: str = Field(
        default="your-admin-session-secret-change-this",
        description="Secret key for admin session encryption",
    )

    # Rate Limiting (based on task.md)
    rate_limit_enabled: bool = True
    rate_limit_per_user_balance: int = 10
    rate_limit_per_user_transactions: int = 20
    rate_limit_global: int = 1000

    # simulator settings
    bank_simulator_min_delay: int = 2  # sec
    bank_simulator_max_delay: int = 10  # sec
    bank_simulator_success_rate: float = 0.9  # 90% - tasks.mds

    # idempotency
    idempotency_key_ttl_hours: int = 24

    # server conf
    server_host: str = Field(default="localhost", description="Server bind host")
    server_port: int = Field(default=8000, description="Server bind port")
    cors_origins: list[str] = Field(
        default=["localhost"],
        description="Allowed CORS origins (use specific domains in production)",
    )

    @property
    def database_url_str(self) -> str:
        return str(self.database_url)

    @property
    def redis_url_str(self) -> str:
        return str(self.redis_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
