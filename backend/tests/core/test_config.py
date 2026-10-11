import pytest

from app.core import config

ENV_NAMES = ["DATABASE_URL", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST", "DB_PORT", "POSTGRES_DB"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: None)
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_explicit_url_wins_over_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://env/db")
    assert config.resolve_database_url("sqlite://explicit") == "sqlite://explicit"


def test_database_url_environment_variable_is_used(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://env/db")
    assert config.resolve_database_url() == "postgresql://env/db"


def test_url_is_composed_from_postgres_variables(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "taskly")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("POSTGRES_HOST", "db.local")
    monkeypatch.setenv("DB_PORT", "5433")
    monkeypatch.setenv("POSTGRES_DB", "todos")
    assert (
        config.resolve_database_url()
        == "postgresql+psycopg://taskly:secret@db.local:5433/todos"
    )


def test_missing_postgres_variables_raise_key_error():
    with pytest.raises(KeyError):
        config.resolve_database_url()
