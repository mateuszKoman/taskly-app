import subprocess
from types import SimpleNamespace

from agent.pipeline import run_pr
from agent.runtime import Agent, Config
from agent.tests.conftest import write
from agent.tests.test_runtime import ScriptedClient, response, text, tool
from agent.tools import Toolbox
from agent.triage import triage
from agent.verify import SuiteResult

TARGET = "backend/app/features/todos/router.py"
NEW_TEST = "backend/tests/features/todos/test_router.py"


def suites(after_passed=True):
    calls = []

    def runner(root, side):
        phase = "before" if not any(c[1] == side for c in calls) else "after"
        calls.append((phase, side))
        passed = True if phase == "before" else after_passed
        return SuiteResult(passed, 0 if passed else 1, 50.0 if phase == "before" else 60.0, "lines", "")
    return runner, calls


def pipeline(repo, client, runner, after_triage=lambda: None):
    result = triage(repo, "main")
    after_triage()  # triage itself shells out to git, so test-run fakes go in afterwards
    make = lambda record: Agent(client, Config(), "system", Toolbox(repo, result, {}, record))
    return run_pr(repo, result, "test-model", make, runner)


def test_nothing_to_do_skips_suites_and_model(repo):
    runner, calls = suites()
    report = pipeline(repo, ScriptedClient(), runner)
    assert report["status"] == "nothing_to_do" and calls == [] and report["check_failed"] is False


def test_red_test_is_dropped_and_suites_bracket_the_run(repo, monkeypatch):
    write(repo, TARGET, "x = 2\n")
    fail = lambda: monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=1, stdout="boom", stderr=""))
    client = ScriptedClient(
        response("tool_use",
                 tool("record_decision", path=TARGET, action="update", reason="new branch"),
                 tool("write_test_file", path=NEW_TEST, content="def test_bad(): assert False\n")),
        response("tool_use", tool("run_tests", target="backend", paths=[NEW_TEST])),
        response("end_turn", text("gave up")),
        response("end_turn", text("gave up")),
        response("end_turn", text("gave up")),
    )
    runner, calls = suites()
    report = pipeline(repo, client, runner, fail)
    assert calls == [("before", "backend"), ("after", "backend")]
    assert report["status"] == "incomplete"
    assert report["dropped"][0]["path"] == NEW_TEST and report["dropped"][0]["last_output"] == "boom"
    assert report["files_written"] == []
    assert (repo / NEW_TEST).read_text() == "def test_ok():\n    assert True\n"
    assert report["suites"]["backend"]["before"]["coverage"] == 50.0
    assert report["check_failed"] is False


def test_failing_final_suite_fails_the_check(repo):
    write(repo, TARGET, "x = 2\n")
    client = ScriptedClient(
        response("tool_use", tool("record_decision", path=TARGET, action="skip", reason="constant")),
        response("end_turn", text("done")),
    )
    report = pipeline(repo, client, suites(after_passed=False)[0])
    assert report["status"] == "ok" and report["check_failed"] is True


def test_agent_crash_is_reported_and_cleaned_up(repo):
    write(repo, TARGET, "x = 2\n")

    class Broken:
        def create(self, **kwargs):
            raise ConnectionError("API unreachable")
    report = pipeline(repo, Broken(), suites()[0])
    assert report["status"] == "error" and report["check_failed"] is True
    assert report["error"] == "ConnectionError: API unreachable"
    assert "after" in report["suites"]["backend"]
