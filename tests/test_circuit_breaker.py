import app.core.circuit_breaker as cb_mod
from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerRegistry


def test_closed_allows_calls() -> None:
    b = CircuitBreaker(failure_threshold=3, recovery_seconds=10)
    assert b.allow() is True


def test_stays_closed_below_threshold() -> None:
    b = CircuitBreaker(failure_threshold=3, recovery_seconds=10)
    b.record_failure()
    b.record_failure()
    assert b.allow() is True


def test_opens_after_threshold_failures() -> None:
    b = CircuitBreaker(failure_threshold=3, recovery_seconds=10)
    b.record_failure()
    b.record_failure()
    b.record_failure()
    assert b.allow() is False


def test_success_resets_failure_count() -> None:
    b = CircuitBreaker(failure_threshold=3, recovery_seconds=10)
    b.record_failure()
    b.record_failure()
    b.record_success()
    b.record_failure()
    b.record_failure()
    assert b.allow() is True  # only 2 consecutive since the reset


def test_open_rejects_until_recovery_window_elapses(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    now = [0.0]
    monkeypatch.setattr(cb_mod.time, "monotonic", lambda: now[0])
    b = CircuitBreaker(failure_threshold=1, recovery_seconds=10)
    b.record_failure()
    assert b.allow() is False
    now[0] = 5
    assert b.allow() is False
    now[0] = 10
    assert b.allow() is True  # half-open trial allowed


def test_half_open_success_closes_breaker(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    now = [0.0]
    monkeypatch.setattr(cb_mod.time, "monotonic", lambda: now[0])
    b = CircuitBreaker(failure_threshold=2, recovery_seconds=10)
    b.record_failure()
    b.record_failure()
    now[0] = 10
    assert b.allow() is True  # half-open
    b.record_success()
    assert b.allow() is True
    b.record_failure()
    assert b.allow() is True  # failure count truly reset — 1 < threshold of 2


def test_half_open_failure_reopens_breaker(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    now = [0.0]
    monkeypatch.setattr(cb_mod.time, "monotonic", lambda: now[0])
    b = CircuitBreaker(failure_threshold=1, recovery_seconds=10)
    b.record_failure()
    now[0] = 10
    assert b.allow() is True  # half-open
    b.record_failure()
    assert b.allow() is False  # re-opened immediately, not another threshold count


def test_registry_gives_each_provider_an_independent_breaker() -> None:
    registry = CircuitBreakerRegistry(["a", "b"], failure_threshold=2, recovery_seconds=10)
    registry.get("a").record_failure()
    registry.get("a").record_failure()
    assert registry.get("a").allow() is False
    assert registry.get("b").allow() is True
