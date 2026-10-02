import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum

Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]
JitterSource = Callable[[], float]


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 4.0
    jitter_ratio: float = 0.2

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("retry delays cannot be negative")
        if self.base_delay_seconds > self.max_delay_seconds:
            raise ValueError("base delay cannot exceed maximum delay")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1")

    def delay_for_retry(self, retry_number: int, jitter_value: float) -> float:
        """Return delay before a retry, where the first retry is number one."""
        if retry_number < 1:
            raise ValueError("retry_number must be at least 1")
        if not 0 <= jitter_value <= 1:
            raise ValueError("jitter_value must be between 0 and 1")

        exponential_delay = self.base_delay_seconds * (2 ** (retry_number - 1))
        bounded_delay = min(exponential_delay, self.max_delay_seconds)
        jitter = bounded_delay * self.jitter_ratio * jitter_value
        return bounded_delay + jitter


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when a circuit rejects a call before reaching the provider."""


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        recovery_seconds: float = 30.0,
        clock: Clock = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        if recovery_seconds <= 0:
            raise ValueError("recovery_seconds must be positive")

        self._failure_threshold = failure_threshold
        self._recovery_seconds = recovery_seconds
        self._clock = clock
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: float | None = None
        self._probe_in_flight = False
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    async def allow_request(self) -> None:
        async with self._lock:
            if self._state is CircuitState.CLOSED:
                return

            now = self._clock()
            if self._state is CircuitState.OPEN:
                assert self._opened_at is not None
                if now - self._opened_at < self._recovery_seconds:
                    raise CircuitOpenError("Primary model circuit is open")
                self._state = CircuitState.HALF_OPEN

            if self._probe_in_flight:
                raise CircuitOpenError("Primary model recovery probe is already running")
            self._probe_in_flight = True

    async def record_success(self) -> None:
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._opened_at = None
            self._probe_in_flight = False

    async def record_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            self._probe_in_flight = False
            if (
                self._state is CircuitState.HALF_OPEN
                or self._failure_count >= self._failure_threshold
            ):
                self._state = CircuitState.OPEN
                self._opened_at = self._clock()

    async def reject_recovery_probe(self) -> None:
        """Release a half-open probe without treating a caller error as instability."""
        async with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = self._clock()
            self._probe_in_flight = False


def default_sleep(delay: float) -> Awaitable[None]:
    return asyncio.sleep(delay)


def default_jitter() -> float:
    return random.random()
