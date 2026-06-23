# `agents` test suite

Centralised tests for the LangGraph multi-agent pipeline, organised by category.

```
tests/
  unit/              fast, isolated — no broker, no LLM, no network (all mocked)
  integration/       cross-component wiring (contracts serialisation, bus, graph)
  regression/        pins for specific previously-fixed bugs
```

> Per-agent colocated suites still live in `src/agents/<agent>/tests/`.
> Both trees are discovered (`testpaths = ["tests", "src/agents"]`).

Required env vars (ANTHROPIC_API_KEY, REDIS_URL, …) are stubbed for collection by
the root `agents/conftest.py`, so no real broker or API key is needed.

## Running

```bash
poetry run pytest                  # everything
poetry run pytest -m unit
poetry run pytest -m integration
poetry run pytest -m regression
poetry run pytest tests/unit
```

`asyncio_mode = "auto"` — async tests need no decorator.

## Conventions

- **unit** — import the symbol under test; mock the LLM provider / bus / MCP
  clients. Mark files with `pytestmark = pytest.mark.unit`.
- **integration** — exercise serialisation across the (simulated) Celery/Redis
  boundary via `model_dump(mode="json")` → `model_validate`, or drive a graph
  with mocked node side-effects.
- **regression** — name the test after the bug; open the docstring with
  `REGRESSION:`.
