from unittest.mock import Mock

from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.features.todos import repository as repository_module
from app.features.todos.models import TodoRecord
from app.features.todos.repository import TodoRepository
from app.features.todos.schemas import TodoCreate


def test_list_maps_models_and_orders_tasks_newest_first(model_factory, todo_values, todo):
    session = Mock(spec=Session)
    session.scalars.return_value = [model_factory(todo_values)]
    assert TodoRepository(session).list() == [todo]
    statement = session.scalars.call_args.args[0]
    expected = select(TodoRecord).order_by(TodoRecord.created_at.desc(), TodoRecord.id.desc())
    assert statement.compare(expected)
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "ORDER BY todos.created_at DESC, todos.id DESC" in compiled


def test_get_returns_none_for_missing_task():
    session = Mock(spec=Session)
    session.get.return_value = None
    assert TodoRepository(session).get(404) is None
    session.get.assert_called_once_with(TodoRecord, 404)


def test_get_returns_mapped_task(model_factory, todo_values, todo):
    session = Mock(spec=Session)
    session.get.return_value = model_factory(todo_values)
    assert TodoRepository(session).get(7) == todo


def test_create_persists_record_with_timestamps(monkeypatch):
    session = Mock(spec=Session)
    monkeypatch.setattr(repository_module, "from_model", lambda record: record)
    record = TodoRepository(session).create(TodoCreate(title="Plan", priority="high"))
    session.add.assert_called_once_with(record)
    session.commit.assert_called_once_with()
    session.refresh.assert_called_once_with(record)
    assert record.title == "Plan"
    assert record.priority == "high"
    assert record.created_at == record.updated_at


def test_update_returns_none_for_missing_task():
    session = Mock(spec=Session)
    session.get.return_value = None
    assert TodoRepository(session).update(404, Mock()) is None
    session.commit.assert_not_called()


def test_update_applies_only_set_fields(monkeypatch, model_factory, todo_values):
    session = Mock(spec=Session)
    record = model_factory(todo_values)
    session.get.return_value = record
    monkeypatch.setattr(repository_module, "from_model", lambda r: r)
    payload = Mock()
    payload.model_dump.return_value = {"title": "New title"}
    result = TodoRepository(session).update(7, payload)
    payload.model_dump.assert_called_once_with(exclude_unset=True)
    assert result is record
    assert record.title == "New title"
    assert record.priority == "high"
    assert record.updated_at > todo_values["updated_at"]
    session.commit.assert_called_once_with()
    session.refresh.assert_called_once_with(record)


def test_delete_returns_false_for_missing_task():
    session = Mock(spec=Session)
    session.get.return_value = None
    assert TodoRepository(session).delete(404) is False
    session.delete.assert_not_called()
    session.commit.assert_not_called()


def test_delete_removes_record(model_factory, todo_values):
    session = Mock(spec=Session)
    record = model_factory(todo_values)
    session.get.return_value = record
    assert TodoRepository(session).delete(7) is True
    session.delete.assert_called_once_with(record)
    session.commit.assert_called_once_with()
