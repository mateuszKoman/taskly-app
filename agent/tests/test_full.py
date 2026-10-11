import json

from agent.full import full_triage
from agent.pipeline import run_full
from agent.runtime import Agent, Config, first_message
from agent.tests.conftest import write
from agent.tests.test_runtime import ScriptedClient, response, text, tool
from agent.tools import Toolbox
from agent.verify import FileCoverage, SuiteResult, read_file_coverage


def suite(*files, coverage=50.0):
    return SuiteResult(True, 0, coverage, "lines", "", list(files))


SUITES = {
    "backend": suite(
        FileCoverage("backend/app/features/todos/router.py", 51.4, [24, 25, 26, 27]),
        FileCoverage("backend/app/core/config.py", 0.0, [1, 2, 4, 5, 8, 9]),
        FileCoverage("backend/app/features/todos/mappers.py", 100.0, []),
    ),
    "frontend": suite(
        FileCoverage("frontend/src/lib/http.ts", 0.0, [3, 4, 9, 10, 12]),
        FileCoverage("frontend/src/features/todos/components/TodoForm.tsx", 95.0, [40]),
    ),
}


def test_full_triage_picks_the_largest_gaps_first(repo):
    result = full_triage(repo, SUITES, threshold=90, max_targets=2)
    assert result.mode == "full" and result.base == "(full)"
    assert [t.path for t in result.targets] == ["backend/app/core/config.py", "frontend/src/lib/http.ts"]
    config, http = result.targets
    assert (config.test_file, config.coverage, config.missing_lines) == (
        "backend/tests/core/test_config.py", 0.0, [1, 2, 4, 5, 8, 9])
    assert http.test_file == "frontend/src/lib/http.test.ts"
    reasons = {i.path: i.reason for i in result.ignored}
    assert reasons["backend/app/features/todos/router.py"] == "coverage 51.40%, beyond this run's 2-target budget"
    assert reasons["backend/app/features/todos/mappers.py"] == "coverage 100.00% meets the 90% threshold"
    assert reasons["frontend/src/features/todos/components/TodoForm.tsx"] == "coverage 95.00% meets the 90% threshold"


def test_first_message_explains_full_mode(repo):
    message = first_message(full_triage(repo, SUITES, max_targets=1))
    assert message.startswith("Full-repo mode: there is no diff.")
    assert '"missing_lines": [' in message


def test_run_full_reuses_the_baseline_and_reports_full_mode(repo):
    calls = []

    def runner(root, side):
        calls.append(side)
        return SUITES[side]

    target = "backend/app/core/config.py"
    client = ScriptedClient(
        response("tool_use", tool("record_decision", path=target, action="skip", reason="settings wiring only")),
        response("end_turn", text("done")),
    )
    make = lambda run_triage, record: Agent(client, Config(), "system", Toolbox(repo, run_triage, {}, record))
    report = run_full(repo, "test-model", make, runner, max_targets=1)
    assert calls == ["backend", "frontend", "backend", "frontend"]  # one baseline per side, one final per side
    assert report["mode"] == "full" and report["status"] == "ok"
    assert [d["path"] for d in report["decisions"]] == [target]
    assert "files" not in report["suites"]["backend"]["before"]


def test_run_full_with_no_gaps_makes_no_model_call(repo):
    report = run_full(repo, "test-model", lambda *a: None, lambda root, side: suite(coverage=100.0))
    assert report["status"] == "nothing_to_do" and report["mode"] == "full"
    assert set(report["suites"]) == {"backend", "frontend"}


def test_read_file_coverage_parses_both_formats(tmp_path):
    (tmp_path / "coverage.json").write_text(json.dumps({"totals": {"percent_covered": 40}, "files": {
        "app/core/config.py": {"summary": {"percent_covered": 12.5}, "missing_lines": [5, 1, 2]},
    }}))
    assert read_file_coverage(tmp_path, "backend", tmp_path) == [
        FileCoverage("backend/app/core/config.py", 12.5, [1, 2, 5])]

    source = str(tmp_path / "frontend/src/lib/http.ts")
    (tmp_path / "coverage-summary.json").write_text(json.dumps({
        "total": {"lines": {"pct": 10}}, source: {"lines": {"pct": 20.0}}}))
    (tmp_path / "coverage-final.json").write_text(json.dumps({source: {
        "statementMap": {"0": {"start": {"line": 3}}, "1": {"start": {"line": 9}}, "2": {"start": {"line": 3}}},
        "s": {"0": 0, "1": 4, "2": 0},
    }}))
    assert read_file_coverage(tmp_path, "frontend", tmp_path) == [
        FileCoverage("frontend/src/lib/http.ts", 20.0, [3])]


def test_read_file_coverage_tolerates_missing_reports(tmp_path):
    assert read_file_coverage(tmp_path, "frontend", tmp_path) == []
