# `mcp-servers` test suite

Centralised tests for the cross-cutting `shared/` package used by every MCP
tool server (circuit breaker, response cache, rate limiter, auth, audit).

```
tests/
  conftest.py        adds mcp-servers/ to sys.path; provides an in-memory FakeRedis
  unit/              fast, isolated — circuit-breaker state machine, cache key derivation
  integration/       cache cache-aside + single-flight stampede protection vs FakeRedis
  regression/        pins for breaker invariants under concurrency
```

> Each server also has its own colocated suite in `<server>/tests/` (e.g.
> `job-board/tests/test_server.py`) that boots that server's FastAPI app via
> `TestClient`. Those run per-server (each rewires `sys.path` to import its local
> `server` module, so they cannot be collected together) — this `tests/` tree is
> deliberately scoped to the shared library.

## Running

```bash
# shared-package suite (from mcp-servers/)
pytest

pytest -m unit
pytest -m integration
pytest -m regression

# a single server's colocated suite
cd job-board && pytest
```

`asyncio_mode = "auto"` — async tests need no decorator. No live Redis is
required: `conftest.FakeRedis` is injected into `ResponseCache._client`.

## Conventions

- **unit** — drive the pure state machine / key derivation directly; monkeypatch
  `shared.circuit_breaker.time.monotonic` to control the clock deterministically.
- **integration** — inject `fake_redis` into the cache and assert cache-aside +
  single-flight behaviour (e.g. one fetch under a concurrent herd).
- **regression** — name the test after the bug; open the docstring with
  `REGRESSION:`.
