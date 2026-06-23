"""Unit tests for the shared async circuit breaker (``shared.circuit_breaker``)."""
from __future__ import annotations

import pytest

import shared.circuit_breaker as cb_module
from shared.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState

pytestmark = pytest.mark.unit


class _FakeClock:
    """Controllable stand-in for the breaker's ``time`` reference.

    We rebind ``circuit_breaker.time`` to an instance of this — never patch the
    real ``time.monotonic``, which the asyncio event loop also reads (patching it
    would freeze ``asyncio.sleep`` and deadlock concurrency tests).
    """

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def monotonic(self) -> float:
        return self.now


async def _ok() -> str:
    return "ok"


async def _boom() -> None:
    raise RuntimeError("upstream down")


async def test_starts_closed() -> None:
    breaker = CircuitBreaker("t.start")
    assert breaker.state is CircuitState.CLOSED
    assert breaker.is_closed is True


async def test_successful_call_returns_result() -> None:
    breaker = CircuitBreaker("t.ok")
    assert await breaker.call(_ok()) == "ok"
    assert breaker.state is CircuitState.CLOSED


async def test_trips_open_after_threshold_consecutive_failures() -> None:
    breaker = CircuitBreaker("t.trip", failure_threshold=3)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            await breaker.call(_boom())
    assert breaker.state is CircuitState.OPEN


async def test_open_breaker_fast_fails_without_running_coro() -> None:
    breaker = CircuitBreaker("t.fastfail", failure_threshold=1)
    with pytest.raises(RuntimeError):
        await breaker.call(_boom())
    assert breaker.state is CircuitState.OPEN

    ran = False

    async def _tracked() -> str:
        nonlocal ran
        ran = True
        return "x"

    with pytest.raises(CircuitOpenError):
        await breaker.call(_tracked())
    assert ran is False  # coro must never be awaited while OPEN


async def test_open_transitions_to_half_open_after_reset_timeout(monkeypatch) -> None:
    clock = _FakeClock(1000.0)
    monkeypatch.setattr(cb_module, "time", clock)

    breaker = CircuitBreaker("t.halfopen", failure_threshold=1, reset_timeout_s=60)
    with pytest.raises(RuntimeError):
        await breaker.call(_boom())
    assert breaker.state is CircuitState.OPEN

    # Advance past the reset timeout; a successful probe should close the breaker.
    clock.now += 61
    assert await breaker.call(_ok()) == "ok"
    assert breaker.state is CircuitState.CLOSED


async def test_half_open_probe_failure_reopens(monkeypatch) -> None:
    clock = _FakeClock(0.0)
    monkeypatch.setattr(cb_module, "time", clock)

    breaker = CircuitBreaker("t.reopen", failure_threshold=1, reset_timeout_s=30)
    with pytest.raises(RuntimeError):
        await breaker.call(_boom())
    clock.now += 31  # now HALF_OPEN on next call
    with pytest.raises(RuntimeError):
        await breaker.call(_boom())
    assert breaker.state is CircuitState.OPEN
