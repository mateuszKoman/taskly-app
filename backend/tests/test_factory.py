from app import factory


def test_create_app_resolves_database_url_and_mounts_routers(monkeypatch):
    seen = []
    monkeypatch.setattr(
        factory, "resolve_database_url", lambda url: seen.append(url) or "resolved://db"
    )
    app = factory.create_app("explicit://db")
    assert seen == ["explicit://db"]
    assert app.state.database_url == "resolved://db"
    assert app.title == "Taskly API"
    paths = set(app.openapi()["paths"])
    assert "/api/todos" in paths
    assert "/api/todos/{todo_id}" in paths
