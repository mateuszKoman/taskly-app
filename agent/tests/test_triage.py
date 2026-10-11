from agent.tests.conftest import run_git, write
import pytest

from agent.triage import glob_regex, triage


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
    write(repo, "frontend/src/App.tsx", "export const App = () => 1\n")
    write(repo, "frontend/src/lib/http.ts", "export const a = 2\n")
    write(repo, "frontend/src/features/todos/types.ts")
    write(repo, "frontend/src/main.tsx")
    write(repo, "frontend/src/styles.css")
    write(repo, "frontend/src/App.test.tsx", "it('changed', () => {})\n")
    write(repo, "frontend/package.json", "{}")

    result = triage(repo, "main")

    targets = {t.path: t for t in result.targets}
    assert set(targets) == {
        "backend/app/core/config.py",
        "backend/app/features/todos/router.py",
        "backend/app/features/todos/validators.py",
        "frontend/src/App.tsx",
        "frontend/src/lib/http.ts",
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
    app, http = targets["frontend/src/App.tsx"], targets["frontend/src/lib/http.ts"]
    assert (app.side, app.test_file, app.test_exists) == ("frontend", "frontend/src/App.test.tsx", True)
    assert (http.test_file, http.test_exists) == ("frontend/src/lib/http.test.ts", False)
    assert reasons["frontend/src/features/todos/types.ts"] == "excluded by frontend coverage config"
    assert reasons["frontend/src/main.tsx"] == "excluded by frontend coverage config"
    assert reasons["frontend/src/styles.css"] == "not TypeScript source"
    assert reasons["frontend/src/App.test.tsx"] == "test file"
    assert reasons["frontend/package.json"] == "not application source"


def test_deleted_and_test_files_are_ignored(repo):
    run_git(repo, "rm", "-q", "backend/app/features/todos/router.py")
    write(repo, "backend/tests/features/todos/test_router.py", "def test_changed():\n    pass\n")
    result = triage(repo, "main")
    assert result.targets == []
    assert {i.reason for i in result.ignored} == {"deleted", "test file"}


def test_frontend_test_file_reuses_existing_twin_extension(repo):
    write(repo, "frontend/src/hooks/useThing.ts")
    write(repo, "frontend/src/hooks/useThing.test.tsx")
    run_git(repo, "add", "frontend/src/hooks/useThing.test.tsx")
    target = triage(repo, "main").target("frontend/src/hooks/useThing.ts")
    assert target.test_file == "frontend/src/hooks/useThing.test.tsx"


@pytest.mark.parametrize("pattern, path, expected", [
    ("src/**/*.{ts,tsx}", "src/a/b/c.tsx", True),
    ("src/**/*.{ts,tsx}", "src/c.ts", True),
    ("src/**/*.{ts,tsx}", "src/c.css", False),
    ("src/main.tsx", "src/main.tsx", True),
    ("src/main.tsx", "src/a/main.tsx", False),
    ("src/*.ts", "src/a/b.ts", False),
    ("src/**/types.ts", "src/types.ts", True),
])
def test_glob_regex(pattern, path, expected):
    assert bool(glob_regex(pattern).match(path)) is expected
