import asyncio
from unittest.mock import Mock

import pytest
from fastapi import FastAPI

from app.core import lifespan as lifespan_module


def _patch(monkeypatch, initialize=None):
    engine = Mock()
    factory = Mock()
    create_engine = Mock(return_value=engine)
    monkeypatch.setattr(lifespan_module, "create_database_engine", create_engine)
    monkeypatch.setattr(lifespan_module, "create_session_factory", Mock(return_value=factory))
    monkeypatch.setattr(lifespan_module, "initialize", initialize or Mock())
    return engine, factory, create_engine


def test_lifespan_sets_session_factory_and_disposes_engine(monkeypatch):
    engine, factory, create_engine = _patch(monkeypatch)
    app = FastAPI()
    app.state.database_url = "sqlite://"

    async def run():
        async with lifespan_module.lifespan(app):
            assert app.state.session_factory is factory
            engine.dispose.assert_not_called()

    asyncio.run(run())
    create_engine.assert_called_once_with("sqlite://")
    lifespan_module.initialize.assert_called_once_with(engine)
    engine.dispose.assert_called_once_with()


def test_lifespan_disposes_engine_when_initialization_fails(monkeypatch):
    engine, _, _ = _patch(monkeypatch, initialize=Mock(side_effect=RuntimeError("boom")))
    app = FastAPI()
    app.state.database_url = "sqlite://"

    async def run():
        async with lifespan_module.lifespan(app):
            pass

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(run())
    engine.dispose.assert_called_once_with()
