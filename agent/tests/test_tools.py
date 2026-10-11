import pytest

from agent.skills import Skill
from agent.tests.conftest import write
from agent.tools import RunRecord, ToolError, Toolbox, safe_env
from agent.triage import triage


@pytest.fixture
def toolbox(repo):
    write(repo, "backend/app/features/todos/router.py", "x = 2\n")
    skills = {"demo": Skill("demo", "a demo skill", "demo body")}
    return Toolbox(repo, triage(repo, "main"), skills, RunRecord())


def test_write_outside_test_paths_is_refused_and_leaves_no_file(toolbox, repo):
    with pytest.raises(ToolError, match="writes are limited"):
        toolbox.call("write_test_file", {"path": "backend/app/evil.py", "content": "x"})
    assert not (repo / "backend/app/evil.py").exists()


def test_write_records_create_and_update(toolbox, repo):
    toolbox.call("write_test_file", {"path": "backend/tests/core/test_new.py", "content": "def test_a(): pass\n"})
    toolbox.call("write_test_file", {"path": "backend/tests/features/todos/test_router.py", "content": "def test_b(): pass\n"})
    assert toolbox.record.files_written == {
        "backend/tests/core/test_new.py": "create",
        "backend/tests/features/todos/test_router.py": "update",
    }
    assert (repo / "backend/tests/core/test_new.py").read_text() == "def test_a(): pass\n"


def test_read_file_refuses_secrets(toolbox, repo):
    write(repo, ".env", "ANTHROPIC_API_KEY=sk-test")
    with pytest.raises(ToolError, match="secrets"):
        toolbox.call("read_file", {"path": ".env"})


def test_git_diff_shows_the_change(toolbox):
    assert "+x = 2" in toolbox.call("git_diff", {"path": "backend/app/features/todos/router.py"})


def test_run_tests_refuses_non_test_paths(toolbox):
    with pytest.raises(ToolError, match="not a backend test file"):
        toolbox.call("run_tests", {"target": "backend", "paths": ["backend/app/features/todos/router.py"]})


def test_run_tests_refuses_unknown_target(toolbox):
    with pytest.raises(ToolError, match="unsupported test target"):
        toolbox.call("run_tests", {"target": "shell", "paths": ["backend/tests/features/todos/test_router.py"]})


def test_run_tests_records_result(toolbox, monkeypatch):
    import sys
    monkeypatch.setenv("AGENT_BACKEND_PYTHON", sys.executable)
    output = toolbox.call("run_tests", {"target": "backend", "paths": ["backend/tests/features/todos/test_router.py"]})
    assert output == "== backend/tests/features/todos/test_router.py: PASSED"
    assert toolbox.record.last_result == {"backend/tests/features/todos/test_router.py": True}


def test_record_decision_only_accepts_triage_targets(toolbox):
    with pytest.raises(ToolError, match="not a triage target"):
        toolbox.call("record_decision", {"path": "README.md", "action": "skip", "reason": "docs"})
    toolbox.call("record_decision", {
        "path": "backend/app/features/todos/router.py", "action": "update", "reason": "new branch",
    })
    assert toolbox.record.decisions["backend/app/features/todos/router.py"]["action"] == "update"


def test_unknown_tool_and_skill_are_errors(toolbox):
    with pytest.raises(ToolError, match="unknown tool"):
        toolbox.call("bash", {"command": "ls"})
    with pytest.raises(ToolError, match="unknown skill"):
        toolbox.call("load_skill", {"name": "nope"})
    assert toolbox.call("load_skill", {"name": "demo"}) == "demo body"
    assert toolbox.record.skills_loaded == ["demo"]


def test_safe_env_strips_secrets(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk")
    monkeypatch.setenv("GITHUB_TOKEN", "gh")
    monkeypatch.setenv("DB_PASSWORD", "pw")
    monkeypatch.setenv("HARMLESS", "ok")
    env = safe_env()
    assert "ANTHROPIC_API_KEY" not in env and "GITHUB_TOKEN" not in env and "DB_PASSWORD" not in env
    assert env["HARMLESS"] == "ok"


def test_frontend_tests_run_vitest_with_a_scrubbed_environment(toolbox, repo, monkeypatch):
    import subprocess
    from types import SimpleNamespace
    write(repo, "frontend/node_modules/.bin/vitest", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk")
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda command, **kw: calls.append((command, kw)) or
                        SimpleNamespace(returncode=1, stdout="1 failed", stderr=""))
    output = toolbox.call("run_tests", {"target": "frontend", "paths": ["frontend/src/App.test.tsx"]})
    command, kw = calls[0]
    assert command[1:] == ["run", "src/App.test.tsx"]
    assert kw["cwd"] == repo.resolve() / "frontend"
    assert "ANTHROPIC_API_KEY" not in kw["env"] and kw["env"]["CI"] == "1"
    assert output.startswith("== frontend/src/App.test.tsx: FAILED (exit code 1, 3 repair(s) left)")
    assert toolbox.record.last_result == {"frontend/src/App.test.tsx": False}


def test_frontend_run_needs_installed_dependencies(toolbox):
    with pytest.raises(ToolError, match="npm ci"):
        toolbox.call("run_tests", {"target": "frontend", "paths": ["frontend/src/App.test.tsx"]})


def test_target_and_path_side_must_agree(toolbox):
    with pytest.raises(ToolError, match="not a frontend test file"):
        toolbox.call("run_tests", {"target": "frontend", "paths": ["backend/tests/features/todos/test_router.py"]})


@pytest.fixture
def failing_runs(monkeypatch):
    import subprocess
    from types import SimpleNamespace
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=1, stdout="AssertionError", stderr=""))


def test_repair_budget_is_enforced(toolbox, repo, failing_runs):
    path = "backend/tests/core/test_new.py"
    toolbox.call("write_test_file", {"path": path, "content": "v1"})
    for _ in range(3):
        toolbox.call("run_tests", {"target": "backend", "paths": [path]})
        toolbox.call("write_test_file", {"path": path, "content": "next"})
    output = toolbox.call("run_tests", {"target": "backend", "paths": [path]})
    assert "repair budget spent" in output
    with pytest.raises(ToolError, match="repair budget is spent"):
        toolbox.call("write_test_file", {"path": path, "content": "one more"})
    assert toolbox.record.failures[path] == 4
    assert toolbox.record.last_output[path] == "AssertionError"


def test_first_write_snapshots_the_original(toolbox):
    existing = "backend/tests/features/todos/test_router.py"
    toolbox.call("write_test_file", {"path": existing, "content": "first"})
    toolbox.call("write_test_file", {"path": existing, "content": "second"})
    toolbox.call("write_test_file", {"path": "backend/tests/core/test_new.py", "content": "x"})
    assert toolbox.record.originals == {
        existing: "def test_ok():\n    assert True\n",
        "backend/tests/core/test_new.py": None,
    }


def test_flag_suspected_bug_needs_a_test_path_and_reason(toolbox):
    with pytest.raises(ToolError, match="writes are limited"):
        toolbox.call("flag_suspected_bug", {"test_file": "backend/app/x.py", "test_name": "t", "reason": "r"})
    with pytest.raises(ToolError, match="must not be empty"):
        toolbox.call("flag_suspected_bug", {"test_file": "backend/tests/test_a.py", "test_name": "t", "reason": " "})
    toolbox.call("flag_suspected_bug", {
        "test_file": "backend/tests/test_a.py", "test_name": "test_x", "reason": "returns None for empty input",
    })
    assert toolbox.record.suspected_bugs == [
        {"test_file": "backend/tests/test_a.py", "test_name": "test_x", "reason": "returns None for empty input"},
    ]
