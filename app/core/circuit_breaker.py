import time
from enum import Enum


class _State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Per-provider failure gate. Trips OPEN after `failure_threshold` consecutive
    failures; rejects calls until `recovery_seconds` has elapsed, then allows ONE
    HALF_OPEN trial call at a time — a success closes it, a failure re-opens it. A trial
    that never reports back is retried after another `recovery_seconds`."""

    def __init__(self, failure_threshold: int, recovery_seconds: float) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_seconds = recovery_seconds
        self._state = _State.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._probe_at = float("-inf")

    def allow(self) -> bool:
        now = time.monotonic()
        if self._state is _State.OPEN:
            if now - self._opened_at < self._recovery_seconds:
                return False
            self._state = _State.HALF_OPEN
        if self._state is _State.HALF_OPEN:
            if now - self._probe_at < self._recovery_seconds:
                return False
            self._probe_at = now
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._state = _State.CLOSED

    def record_neutral(self) -> None:
        """The call ended with a client/quota error, not a provider verdict: free a half-open
        trial slot without closing or re-opening the breaker."""
        self._probe_at = float("-inf")

    def record_failure(self) -> None:
        self._failures += 1
        if self._state is _State.HALF_OPEN or self._failures >= self._failure_threshold:
            self._state = _State.OPEN
            self._opened_at = time.monotonic()


class CircuitBreakerRegistry:
    def __init__(
        self, provider_ids: list[str], failure_threshold: int, recovery_seconds: float
    ) -> None:
        self._breakers = {
            provider_id: CircuitBreaker(failure_threshold, recovery_seconds)
            for provider_id in provider_ids
        }

    def get(self, provider_id: str) -> CircuitBreaker:
        return self._breakers[provider_id]
