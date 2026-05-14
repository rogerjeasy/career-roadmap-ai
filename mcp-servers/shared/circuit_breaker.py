"""Async circuit breaker for upstream API calls in MCP servers.

State machine:
  CLOSED    → requests pass through; failure counter increments on each error
  OPEN      → fast-fails all calls after failure_threshold errors; transitions
              to HALF_OPEN after reset_timeout_s
  HALF_OPEN → admits a limited probe call; success → CLOSED, failure → OPEN

Breaker instances are created per (server, source) so a single upstream
outage does not cascade to unrelated sources. The current state is exported
as a Prometheus Gauge so alerts can page on OPEN breakers.

Usage::

    breaker = CircuitBreaker("job_board.linkedin")
    try:
        result = await breaker.call(my_coro())
    except CircuitOpenError:
        return []   # fast-fail — no upstream call made
"""
from __future__ import annotations

import asyncio
import enum
import time
from collections.abc import Coroutine
from typing import Any, TypeVar

import structlog
from prometheus_client import Counter, Gauge

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class CircuitState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when a call is rejected because the circuit is OPEN."""

    def __init__(self, breaker_name: str) -> None:
        super().__init__(f"Circuit '{breaker_name}' is OPEN — fast-failing request")
        self.breaker_name = breaker_name


# ── Global Prometheus metrics (shared across all breaker instances) ────────────

_BREAKER_STATE = Gauge(
    "mcp_circuit_breaker_state",
    "Circuit breaker state: 0=closed, 1=open, 2=half_open",
    ["breaker"],
)

_BREAKER_TRIPS = Counter(
    "mcp_circuit_breaker_trips_total",
    "Total times a circuit breaker tripped from CLOSED to OPEN",
    ["breaker"],
)

_BREAKER_REJECTIONS = Counter(
    "mcp_circuit_breaker_rejections_total",
    "Requests fast-failed because the circuit was OPEN",
    ["breaker"],
)

_BREAKER_RECOVERIES = Counter(
    "mcp_circuit_breaker_recoveries_total",
    "Total times a circuit breaker recovered from OPEN to CLOSED",
    ["breaker"],
)

_STATE_NUMERIC = {
    CircuitState.CLOSED: 0,
    CircuitState.OPEN: 1,
    CircuitState.HALF_OPEN: 2,
}


class CircuitBreaker:
    """Async-safe circuit breaker.

    Args:
        name: Unique identifier used in logs and Prometheus labels.
            Convention: ``"<server>.<source>"``, e.g. ``"job_board.linkedin"``.
        failure_threshold: Number of consecutive failures before tripping OPEN.
        reset_timeout_s: Seconds in OPEN state before transitioning to HALF_OPEN.
        half_open_max_calls: Concurrent probe calls allowed in HALF_OPEN state.
    """

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        reset_timeout_s: float = 60.0,
        half_open_max_calls: int = 1,
    ) -> None:
        self.name = name
        self._failure_threshold = failure_threshold
        self._reset_timeout_s = reset_timeout_s
        self._half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_active = 0
        self._lock = asyncio.Lock()

        _BREAKER_STATE.labels(breaker=self.name).set(_STATE_NUMERIC[self._state])

    # ── Public API ────────────────────────────────────────────────────────────

    async def call(self, coro: Coroutine[Any, Any, T]) -> T:
        """Execute *coro* under the circuit breaker.

        Raises:
            CircuitOpenError: if the circuit is OPEN (fast-fail).
            Any exception propagated from *coro* (and counted as a failure).
        """
        async with self._lock:
            state = await self._current_state()
            if state == CircuitState.OPEN:
                _BREAKER_REJECTIONS.labels(breaker=self.name).inc()
                raise CircuitOpenError(self.name)
            if state == CircuitState.HALF_OPEN:
                if self._half_open_active >= self._half_open_max_calls:
                    _BREAKER_REJECTIONS.labels(breaker=self.name).inc()
                    raise CircuitOpenError(self.name)
                self._half_open_active += 1

        try:
            result = await coro
            await self._on_success()
            return result
        except Exception:
            await self._on_failure()
            raise

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def is_closed(self) -> bool:
        return self._state == CircuitState.CLOSED

    # ── Internal state machine ────────────────────────────────────────────────

    async def _current_state(self) -> CircuitState:
        """Re-evaluate state transitions; call while holding self._lock."""
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self._reset_timeout_s:
                self._transition(CircuitState.HALF_OPEN)
        return self._state

    async def _on_success(self) -> None:
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_active = max(0, self._half_open_active - 1)
                self._transition(CircuitState.CLOSED)
                _BREAKER_RECOVERIES.labels(breaker=self.name).inc()
                logger.info(
                    "circuit_breaker.recovered",
                    breaker=self.name,
                    new_state="closed",
                )
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0

    async def _on_failure(self) -> None:
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_active = max(0, self._half_open_active - 1)
                self._transition(CircuitState.OPEN)
                logger.warning(
                    "circuit_breaker.half_open_probe_failed",
                    breaker=self.name,
                    new_state="open",
                )
            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1
                self._last_failure_time = time.monotonic()
                if self._failure_count >= self._failure_threshold:
                    self._transition(CircuitState.OPEN)
                    _BREAKER_TRIPS.labels(breaker=self.name).inc()
                    logger.error(
                        "circuit_breaker.tripped",
                        breaker=self.name,
                        failure_count=self._failure_count,
                        reset_in_s=self._reset_timeout_s,
                    )

    def _transition(self, new_state: CircuitState) -> None:
        self._state = new_state
        _BREAKER_STATE.labels(breaker=self.name).set(_STATE_NUMERIC[new_state])
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._half_open_active = 0
