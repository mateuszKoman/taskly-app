import pytest

from app.features.todos.schemas import TodoCreate


def test_list_returns_tasks_from_repository(client, repository_mock, todo):
    repository_mock.list.return_value = [todo]
    response = client.get("/api/todos")
    assert response.status_code == 200
    assert response.json() == [todo.model_dump(mode="json")]
    repository_mock.list.assert_called_once_with()


def test_list_due_soon_asks_repository_for_due_soon_tasks(client, repository_mock, todo):
    repository_mock.list.return_value = [todo]
    response = client.get("/api/todos", params={"due_soon": "true"})
    assert response.status_code == 200
    assert response.json() == [todo.model_dump(mode="json")]
    repository_mock.list.assert_called_once_with(due_soon=True)


def test_list_due_soon_false_uses_default_listing(client, repository_mock):
    repository_mock.list.return_value = []
    assert client.get("/api/todos", params={"due_soon": "false"}).status_code == 200
    repository_mock.list.assert_called_once_with()


def test_create_trims_input_and_returns_created_task(client, repository_mock, todo):
    repository_mock.create.return_value = todo
    response = client.post("/api/todos", json={"title": "  Plan the sprint  ", "priority": "high"})
    assert response.status_code == 201
    assert response.json() == todo.model_dump(mode="json")
    repository_mock.create.assert_called_once_with(
        TodoCreate(title="Plan the sprint", priority="high")
    )


@pytest.mark.parametrize("payload", [
    {"title": "   "},
    {"title": "x" * 121},
    {"title": "Task", "priority": "urgent"},
    {"title": "Task", "due_date": "2026-02-30"},
])
def test_invalid_create_never_calls_repository(client, repository_mock, payload):
    assert client.post("/api/todos", json=payload).status_code == 422
    repository_mock.create.assert_not_called()


def test_get_returns_task(client, repository_mock, todo):
    repository_mock.get.return_value = todo
    response = client.get("/api/todos/7")
    assert response.status_code == 200
    assert response.json() == todo.model_dump(mode="json")
    repository_mock.get.assert_called_once_with(7)


def test_get_missing_task_returns_404(client, repository_mock):
    repository_mock.get.return_value = None
    response = client.get("/api/todos/9")
    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found."}


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_non_positive_id_is_rejected_without_repository_call(client, repository_mock, method):
    kwargs = {"json": {"completed": True}} if method == "patch" else {}
    assert getattr(client, method)("/api/todos/0", **kwargs).status_code == 422
    repository_mock.get.assert_not_called()
    repository_mock.update.assert_not_called()
    repository_mock.delete.assert_not_called()


def test_update_returns_updated_task(client, repository_mock, todo):
    repository_mock.update.return_value = todo
    response = client.patch("/api/todos/7", json={"completed": True})
    assert response.status_code == 200
    assert response.json() == todo.model_dump(mode="json")
    repository_mock.update.assert_called_once()
    assert repository_mock.update.call_args.args[0] == 7


def test_update_missing_task_returns_404(client, repository_mock):
    repository_mock.update.return_value = None
    response = client.patch("/api/todos/7", json={"completed": True})
    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found."}


def test_delete_returns_204(client, repository_mock):
    repository_mock.delete.return_value = True
    response = client.delete("/api/todos/7")
    assert response.status_code == 204
    assert response.content == b""
    repository_mock.delete.assert_called_once_with(7)


def test_delete_missing_task_returns_404(client, repository_mock):
    repository_mock.delete.return_value = False
    response = client.delete("/api/todos/7")
    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found."}
