"""Regression tests pinning circuit-breaker invariants under load."""
from __future__ import annotations

import asyncio

import pytest

import shared.circuit_breaker as cb_module
from shared.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState

pytestmark = pytest.mark.regression


class _FakeClock:
    """Controllable clock injected via ``circuit_breaker.time``.

    Rebinding the module's ``time`` reference (rather than patching the real
    ``time.monotonic``) keeps the asyncio event loop's clock real, so
    ``asyncio.sleep`` in the concurrency tests below still elapses.
    """

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def monotonic(self) -> float:
        return self.now


async def _ok() -> str:
    return "ok"


async def _boom() -> None:
    raise RuntimeError("down")


async def test_failures_must_be_consecutive_to_trip() -> None:
    # REGRESSION: an intermittently-failing upstream must NOT trip the breaker —
    # a single success has to reset the consecutive-failure counter.
    breaker = CircuitBreaker("reg.consecutive", failure_threshold=3)

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await breaker.call(_boom())
    await breaker.call(_ok())  # resets the counter
    for _ in range(2):
        with pytest.raises(RuntimeError):
            await breaker.call(_boom())

    assert breaker.state is CircuitState.CLOSED  # 2 < threshold after reset


async def test_half_open_admits_only_one_probe_at_a_time(monkeypatch) -> None:
    # REGRESSION: in HALF_OPEN the breaker must admit a single probe; a second
    # concurrent caller must be fast-failed, not allowed to hammer a recovering
    # upstream.
    clock = _FakeClock(0.0)
    monkeypatch.setattr(cb_module, "time", clock)

    breaker = CircuitBreaker(
        "reg.halfopen_probe", failure_threshold=1, reset_timeout_s=10, half_open_max_calls=1
    )
    with pytest.raises(RuntimeError):
        await breaker.call(_boom())
    assert breaker.state is CircuitState.OPEN

    clock.now += 11  # eligible for HALF_OPEN on next call

    async def slow_probe() -> str:
        await asyncio.sleep(0.05)
        return "recovered"

    rejected = False

    async def second_probe() -> str:
        nonlocal rejected
        try:
            return await breaker.call(_ok())
        except CircuitOpenError:
            rejected = True
            return "rejected"

    probe, second = await asyncio.gather(breaker.call(slow_probe()), second_probe())
    assert probe == "recovered"
    assert rejected is True
    assert breaker.state is CircuitState.CLOSED  # the admitted probe succeeded


async def test_open_breaker_does_not_leak_failure_count_into_closed(monkeypatch) -> None:
    # REGRESSION: after recovery the failure counter must be zeroed so the very
    # next failure does not instantly re-trip a freshly-closed breaker.
    clock = _FakeClock(0.0)
    monkeypatch.setattr(cb_module, "time", clock)

    breaker = CircuitBreaker("reg.reset_count", failure_threshold=2, reset_timeout_s=5)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            await breaker.call(_boom())
    assert breaker.state is CircuitState.OPEN

    clock.now += 6
    await breaker.call(_ok())  # HALF_OPEN probe → CLOSED, count reset
    assert breaker.state is CircuitState.CLOSED

    with pytest.raises(RuntimeError):
        await breaker.call(_boom())  # a single failure must not re-trip (threshold=2)
    assert breaker.state is CircuitState.CLOSED
