from agent.tests.conftest import run_git, write
from agent.triage import triage


def test_nothing_changed_yields_no_targets(repo):
    result = triage(repo, "main")
    assert result.targets == [] and result.ignored == []


def test_classifies_committed_and_uncommitted_changes(repo):
    run_git(repo, "checkout", "-q", "-b", "feature")
    write(repo, "backend/app/features/todos/router.py", "x = 2\n")
    write(repo, "backend/app/features/todos/validators.py")
    write(repo, "backend/app/features/todos/schemas.py")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-q", "-m", "feature")
    write(repo, "backend/app/core/config.py")  # untracked
    write(repo, "README.md", "changed\n")  # uncommitted
    write(repo, "agent/runtime.py")
    write(repo, "frontend/src/App.tsx")

    result = triage(repo, "main")

    targets = {t.path: t for t in result.targets}
    assert set(targets) == {
        "backend/app/core/config.py",
        "backend/app/features/todos/router.py",
        "backend/app/features/todos/validators.py",
    }
    router = targets["backend/app/features/todos/router.py"]
    assert router.test_file == "backend/tests/features/todos/test_router.py"
    assert router.test_exists is True
    assert targets["backend/app/core/config.py"].test_file == "backend/tests/core/test_config.py"
    assert targets["backend/app/core/config.py"].test_exists is False
    reasons = {i.path: i.reason for i in result.ignored}
    assert reasons["backend/app/features/todos/schemas.py"] == "excluded by backend coverage config"
    assert reasons["README.md"] == "not application source"
    assert reasons["agent/runtime.py"].startswith("agent code")
    assert "frontend/src/App.tsx" in reasons


def test_deleted_and_test_files_are_ignored(repo):
    run_git(repo, "rm", "-q", "backend/app/features/todos/router.py")
    write(repo, "backend/tests/features/todos/test_router.py", "def test_changed():\n    pass\n")
    result = triage(repo, "main")
    assert result.targets == []
    assert {i.reason for i in result.ignored} == {"deleted", "test file"}
