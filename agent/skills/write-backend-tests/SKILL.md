---
name: write-backend-tests
description: Writing or updating pytest tests for backend targets (backend/app).
---

# Write backend tests

Tests mirror the source tree: `app/features/todos/router.py` is tested in `tests/features/todos/test_router.py`. Write the whole file with `write_test_file`; for an update, keep every existing test and add yours.

## Conventions in this repo

- Plain pytest functions named `test_<behaviour>`, one behaviour each, no test classes. Use `pytest.mark.parametrize` for input tables.
- Shared fixtures live in `tests/conftest.py`; read it first and reuse them:
  - `client`: a `TestClient` with only the todos router mounted and `get_repository` overridden by `repository_mock`.
  - `repository_mock`: a `create_autospec` mock of `TodoRepository` from `tests/mocks.py`.
  - `todo_values`, `todo`, `model_factory`: canonical todo data, schema and ORM record.
- Router tests go through `client` and assert both the response and the repository call (`assert_called_once_with`, `assert_not_called`).
- Repository tests pass a `Mock(spec=Session)` and inspect the SQLAlchemy statement; no real database.
- Anything app-level (factory, lifespan, settings) is tested with mocks or `monkeypatch` for environment variables, never a live Postgres.
- Imports are absolute from `app.` and `tests.`.

## Before running

Check every fixture you use exists in `conftest.py` or your file, and every name you import exists in the source you read.
