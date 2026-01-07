import asyncio
import os
from collections.abc import Generator
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.domain.services.auth_service import AuthService
from app.infrastructure.database.base import Base
from app.infrastructure.database.session import get_db
from app.infrastructure.models import Account, User
from app.main import app

TEST_DATABASE_NAME = "payment_gateway_test"
ADMIN_DATABASE_NAME = "postgres"


def _get_db_host() -> str:
    if os.getenv("DB_HOST"):
        return os.getenv("DB_HOST")
    if os.path.exists("/.dockerenv"):
        return "postgres"
    return "localhost"


def _build_test_database_url() -> str:
    if os.getenv("TEST_DATABASE_URL"):
        return os.getenv("TEST_DATABASE_URL")

    prod_url = str(settings.database_url)
    parts = prod_url.split("@")
    if len(parts) != 2:
        raise ValueError(f"Invalid database URL format: {prod_url}")

    credentials_part = parts[0]
    location_part = parts[1]

    db_host = _get_db_host()
    location_parts = location_part.split("/")
    port_and_host = location_parts[0].split(":")[1]

    test_url = f"{credentials_part}@{db_host}:{port_and_host}/{TEST_DATABASE_NAME}"

    return test_url


TEST_DATABASE_URL = _build_test_database_url()
ADMIN_DATABASE_URL = TEST_DATABASE_URL.rsplit("/", 1)[0] + f"/{ADMIN_DATABASE_NAME}"

test_engine = create_engine(
    TEST_DATABASE_URL,
    pool_pre_ping=True,
    echo=False,
    isolation_level="REPEATABLE READ",
)

TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def pytest_configure(config):
    admin_engine = create_engine(ADMIN_DATABASE_URL, isolation_level="AUTOCOMMIT")

    with admin_engine.connect() as conn:
        result = conn.execute(
            text(f"SELECT 1 FROM pg_database WHERE datname = '{TEST_DATABASE_NAME}'")
        )
        exists = result.scalar() is not None

        if not exists:
            conn.execute(text(f"CREATE DATABASE {TEST_DATABASE_NAME}"))
            print(f"\nCreated test database: {TEST_DATABASE_NAME}")
        else:
            print(f"\nTest database already exists: {TEST_DATABASE_NAME}")

    admin_engine.dispose()

    Base.metadata.create_all(bind=test_engine)
    print("Created all tables in test database")


def pytest_unconfigure(config):  # noqa: ARG001
    test_engine.dispose()
    admin_engine = create_engine(ADMIN_DATABASE_URL, isolation_level="AUTOCOMMIT")

    with admin_engine.connect() as conn:
        conn.execute(
            text(
                f"""
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = '{TEST_DATABASE_NAME}'
                  AND pid <> pg_backend_pid()
                """
            )
        )

        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DATABASE_NAME}"))
        print(f"----\nDropped test database: {TEST_DATABASE_NAME}")

    admin_engine.dispose()


class FakeRedis:

    def __init__(self):
        self._data = {}
        self._expiry = {}
        import threading

        self._lock = threading.RLock()

    async def set(self, key: str, value: str, ex: int = None, nx: bool = False) -> bool:
        with self._lock:
            if nx and key in self._data:
                return False
            self._data[key] = value
            if ex:
                self._expiry[key] = ex
            return True

    async def get(self, key: str) -> str | None:
        with self._lock:
            return self._data.get(key)

    async def delete(self, *keys: str) -> int:
        with self._lock:
            count = 0
            for key in keys:
                if key in self._data:
                    del self._data[key]
                    count += 1
            return count

    async def exists(self, key: str) -> int:
        with self._lock:
            return 1 if key in self._data else 0

    async def eval(self, script: str, num_keys: int, *args) -> int:
        with self._lock:
            key = args[0] if args else None
            value = args[1] if len(args) > 1 else None

            if key and key in self._data and self._data.get(key) == value:
                del self._data[key]
                return 1
            return 0

    async def aclose(self):
        pass

    def reset(self):
        with self._lock:
            self._data.clear()
            self._expiry.clear()


@pytest.fixture(scope="function")
def fake_redis():
    redis = FakeRedis()
    yield redis
    redis.reset()


@pytest.fixture(scope="function")
def db() -> Generator[Session, None, None]:
    session = TestSessionLocal()

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

        with test_engine.connect() as conn:
            conn.execute(text("SET session_replication_role = 'replica'"))
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(text(f"TRUNCATE TABLE {table.name} CASCADE"))

            conn.execute(text("SET session_replication_role = 'origin'"))
            conn.commit()


@pytest.fixture(scope="function")
def client(db: Session, fake_redis: FakeRedis, monkeypatch) -> Generator[TestClient, None, None]:
    from app import config
    from app.infrastructure.cache.redis_client import RedisClient, get_cache

    monkeypatch.setattr(config.settings, "rate_limit_enabled", False)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    async def override_get_cache():
        return fake_redis

    def mock_celery_task(*args, **kwargs):  # noqa: ARG001
        task_mock = MagicMock()
        task_mock.id = f"task-{uuid4().hex[:12]}"
        return task_mock

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_cache] = override_get_cache

    monkeypatch.setattr("app.infrastructure.cache.redis_client.get_cache", override_get_cache)
    monkeypatch.setattr("app.api.middleware.idempotency.get_cache", override_get_cache)

    with (
        patch(
            "app.workers.tasks.deposit_tasks.process_deposit.delay", side_effect=mock_celery_task
        ),
        patch(
            "app.workers.tasks.withdrawal_tasks.process_withdrawal.delay",
            side_effect=mock_celery_task,
        ),
    ):

        with TestClient(app) as test_client:
            yield test_client

    app.dependency_overrides.clear()
    RedisClient._instance = None


@pytest.fixture
def test_user(db: Session) -> User:
    auth_service = AuthService(db)
    user = auth_service.register_user(
        email="test@example.com",
        full_name="Test User",
        password="password123",
    )
    return user


@pytest.fixture
def test_account(db: Session, test_user: User) -> Account:
    from app.infrastructure.repositories.account_repository import AccountRepository

    account_repo = AccountRepository(db)
    account = account_repo.get_by_user_id(test_user.id)
    return account


@pytest.fixture
def test_user_with_balance(db: Session) -> tuple[User, Account]:
    from app.infrastructure.repositories.account_repository import AccountRepository

    auth_service = AuthService(db)
    user = auth_service.register_user(
        email="rich@example.com",
        full_name="Rich User",
        password="password123",
    )

    account_repo = AccountRepository(db)
    account = account_repo.get_by_user_id(user.id)
    account.balance = Decimal("1000.00")
    db.commit()
    db.refresh(account)

    return user, account


@pytest.fixture
def auth_token(client: TestClient, test_user: User) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def auth_headers(auth_token: str) -> dict:
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="function")
def event_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture
def mock_bank_success(monkeypatch):
    from uuid import uuid4

    from app.infrastructure.external.bank_simulator import (
        BankResponse,
        BankResponseStatus,
        BankSimulator,
    )

    async def mock_process_deposit(*args, **kwargs):  # noqa: ARG001
        return BankResponse(
            status=BankResponseStatus.SUCCESS,
            transaction_id=f"BANK-{uuid4().hex[:12]}",
            message="Success",
        )

    async def mock_process_withdrawal(*args, **kwargs):  # noqa: ARG001
        return BankResponse(
            status=BankResponseStatus.SUCCESS,
            transaction_id=f"BANK-{uuid4().hex[:12]}",
            message="Success",
        )

    monkeypatch.setattr(BankSimulator, "process_deposit", mock_process_deposit)
    monkeypatch.setattr(BankSimulator, "process_withdrawal", mock_process_withdrawal)


@pytest.fixture
def mock_bank_failure(monkeypatch):
    from app.infrastructure.external.bank_simulator import (
        BankResponse,
        BankResponseStatus,
        BankSimulator,
    )

    async def mock_process_deposit(*args, **kwargs):  # noqa: ARG001
        return BankResponse(
            status=BankResponseStatus.UNAVAILABLE,
            message="Bank service unavailable",
            error_code="BANK_UNAVAILABLE",
        )

    async def mock_process_withdrawal(*args, **kwargs):  # noqa: ARG001
        return BankResponse(
            status=BankResponseStatus.UNAVAILABLE,
            message="Bank service unavailable",
            error_code="BANK_UNAVAILABLE",
        )

    monkeypatch.setattr(BankSimulator, "process_deposit", mock_process_deposit)
    monkeypatch.setattr(BankSimulator, "process_withdrawal", mock_process_withdrawal)
