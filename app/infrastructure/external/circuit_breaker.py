import time
from collections.abc import Callable
from datetime import UTC, datetime
from enum import Enum
from threading import Lock

from app.core.logging import get_logger

logger = get_logger(__name__)


class CircuitState(str, Enum):
    CLOSED = "CLOSED"  # normal
    OPEN = "OPEN"  # fail, reject all requests
    HALF_OPEN = "HALF_OPEN"  # testing if service recovered


class CircuitBreakerOpenError(Exception):
    pass


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        timeout_seconds: int = 30,
        success_threshold: int = 2,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.success_threshold = success_threshold

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: float | None = None
        self.lock = Lock()

        logger.info(
            "circuit_breaker_initialized",
            name=self.name,
            failure_threshold=self.failure_threshold,
            timeout_seconds=self.timeout_seconds,
        )

    def can_execute(self) -> bool:
        with self.lock:
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._transition_to_half_open()
                    return True
                return False

            if self.state == CircuitState.HALF_OPEN:
                return True

            return False

    def record_success(self) -> None:
        with self.lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                logger.info(
                    "circuit_breaker_success",
                    name=self.name,
                    success_count=self.success_count,
                    success_threshold=self.success_threshold,
                )

                if self.success_count >= self.success_threshold:
                    self._transition_to_closed()
            else:
                self.failure_count = 0

    def record_failure(self) -> None:
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            logger.warning(
                "circuit_breaker_failure",
                name=self.name,
                failure_count=self.failure_count,
                failure_threshold=self.failure_threshold,
                state=self.state,
            )

            if self.state == CircuitState.HALF_OPEN:
                self._transition_to_open()
            elif self.state == CircuitState.CLOSED:
                if self.failure_count >= self.failure_threshold:
                    self._transition_to_open()

    def _should_attempt_reset(self) -> bool:
        if self.last_failure_time is None:
            return False

        elapsed = time.time() - self.last_failure_time
        return elapsed >= self.timeout_seconds

    def _transition_to_open(self) -> None:
        self.state = CircuitState.OPEN
        self.success_count = 0

        logger.error(
            "circuit_breaker_opened",
            name=self.name,
            failure_count=self.failure_count,
            timestamp=datetime.now(UTC).isoformat(),
        )

    def _transition_to_half_open(self) -> None:
        self.state = CircuitState.HALF_OPEN
        self.failure_count = 0
        self.success_count = 0

        logger.info(
            "circuit_breaker_half_opened",
            name=self.name,
            timestamp=datetime.now(UTC).isoformat(),
        )

    def _transition_to_closed(self) -> None:
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0

        logger.info(
            "circuit_breaker_closed",
            name=self.name,
            timestamp=datetime.now(UTC).isoformat(),
        )

    def get_state(self) -> dict:
        return {
            "name": self.name,
            "state": self.state,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "failure_threshold": self.failure_threshold,
            "timeout_seconds": self.timeout_seconds,
            "last_failure_time": self.last_failure_time,
        }


def circuit_breaker_decorator(circuit: CircuitBreaker):
    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            if not circuit.can_execute():
                logger.warning(
                    "circuit_breaker_rejected",
                    circuit_name=circuit.name,
                    function=func.__name__,
                )
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{circuit.name}' is OPEN. Service unavailable."
                )

            try:
                result = await func(*args, **kwargs)
                circuit.record_success()
                return result
            except Exception as e:
                circuit.record_failure()
                raise e

        return wrapper

    return decorator
