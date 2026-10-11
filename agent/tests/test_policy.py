import pytest

from agent.policy import PathPolicy, PolicyError, is_test_path, normalize


@pytest.mark.parametrize("path", ["", "   ", "/etc/passwd", "../outside", "backend/../../x", "a\\b", "a\x00b"])
def test_normalize_refuses_unsafe_paths(path):
    with pytest.raises(PolicyError):
        normalize(path)


def test_normalize_drops_dot_segments():
    assert normalize("./backend/./tests/test_a.py") == "backend/tests/test_a.py"


@pytest.mark.parametrize("path", [
    "backend/tests/test_health.py",
    "backend/tests/features/todos/test_router.py",
    "frontend/src/App.test.tsx",
    "frontend/src/features/todos/utils/todos.test.ts",
])
def test_allowed_test_paths(path):
    assert is_test_path(path)


@pytest.mark.parametrize("path", [
    "backend/app/main.py",
    "backend/tests/conftest.py",
    "backend/tests/mocks.py",
    "backend/tests/test_x.txt",
    "frontend/src/App.tsx",
    "frontend/vite.config.ts",
    ".github/workflows/agent.yml",
    "agent/tests/test_policy.py",
    "backend/tests/../app/test_main.py",
])
def test_refused_test_paths(path):
    assert not is_test_path(path)


def test_writable_test_refuses_source(tmp_path):
    with pytest.raises(PolicyError, match="writes are limited"):
        PathPolicy(tmp_path).writable_test("backend/app/main.py")


def test_symlinked_directory_is_refused(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "tests").symlink_to(outside)
    with pytest.raises(PolicyError, match="symlinks"):
        PathPolicy(tmp_path).writable_test("backend/tests/test_escape.py")


def test_symlinked_file_is_refused(tmp_path):
    (tmp_path / "target.txt").write_text("secret")
    (tmp_path / "link.txt").symlink_to(tmp_path / "target.txt")
    with pytest.raises(PolicyError, match="symlinks"):
        PathPolicy(tmp_path).readable("link.txt")


@pytest.mark.parametrize("path", [".env", "backend/.env.local", "deploy/server.pem", "id_rsa"])
def test_secrets_are_never_readable(tmp_path, path):
    with pytest.raises(PolicyError, match="secrets"):
        PathPolicy(tmp_path).readable(path)


@pytest.mark.parametrize("path", [".git/config", "frontend/node_modules/x/index.js", "backend/.venv/bin/python"])
def test_excluded_directories_are_not_readable(tmp_path, path):
    with pytest.raises(PolicyError, match="excluded directory"):
        PathPolicy(tmp_path).readable(path)


def test_env_example_is_readable(tmp_path):
    (tmp_path / ".env.example").write_text("A=1")
    rel, _ = PathPolicy(tmp_path).readable(".env.example")
    assert rel == ".env.example"
