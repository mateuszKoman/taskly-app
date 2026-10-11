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
    assert output.startswith("PASSED")
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
