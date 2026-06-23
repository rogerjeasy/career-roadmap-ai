# `apps/api` test suite

Centralised tests for the FastAPI backend, organised by category.

```
tests/
  conftest.py        shared fixtures: env safety-net, auth users, make_app/client factory, mock repos
  unit/              fast, isolated — no network/DB/Firestore; all I/O mocked
  integration/       cross-layer wiring — real routers + middleware + DI overrides via TestClient
  regression/        pins for specific previously-fixed bugs (must not silently return)
```

> Legacy per-domain tests still live next to their domain in `src/domains/<name>/tests/`.
> Both trees are discovered (`testpaths = ["tests", "src"]` in `pyproject.toml`).

## Running

```bash
# everything
poetry run pytest

# one category (markers are also applied per file)
poetry run pytest -m unit
poetry run pytest -m integration
poetry run pytest -m regression

# one folder
poetry run pytest tests/unit
```

`asyncio_mode = "auto"` — async test functions need no `@pytest.mark.asyncio`.

## Conventions

- **Unit** — import the unit under test directly; mock every dependency with
  `unittest.mock.AsyncMock`/`MagicMock`. No FastAPI app. Mark with
  `pytestmark = pytest.mark.unit`.
- **Integration** — use the `make_app` / `client_factory` fixtures to mount the
  *real* router with `dependency_overrides` for the service + `get_current_user`.
  Pass `case_conversion=True` to also assert the camelCase wire contract.
- **Regression** — name the test after the bug and start the docstring with
  `REGRESSION:` describing what must never break again.

## Adding a controller integration test

```python
from src.endpoints.v1.<name>_controller import router
from src.domains.<name>.service import get_<name>_service

@pytest.fixture
def client(make_app, user):
    app = make_app(
        router=router,
        overrides={get_<name>_service: lambda: FakeService()},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)
```

No live Redis/Firestore/Firebase is required: the app lifespan never runs (the
client is built without the `with` context manager) and every dependency the
handler needs is supplied through `overrides`.
