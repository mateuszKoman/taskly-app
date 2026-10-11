import json
import subprocess

from agent.tests.conftest import write
from agent.tools import RunRecord
from agent.verify import drop_red_tests, read_coverage, run_suite


def test_drop_red_tests_restores_updates_and_deletes_creations(tmp_path):
    write(tmp_path, "backend/tests/test_updated.py", "agent version")
    write(tmp_path, "backend/tests/test_created.py", "agent version")
    write(tmp_path, "backend/tests/test_green.py", "agent version")
    record = RunRecord(
        files_written={"backend/tests/test_updated.py": "update", "backend/tests/test_created.py": "create",
                       "backend/tests/test_green.py": "create"},
        originals={"backend/tests/test_updated.py": "original", "backend/tests/test_created.py": None,
                   "backend/tests/test_green.py": None},
        last_result={"backend/tests/test_updated.py": False, "backend/tests/test_green.py": True},
        failures={"backend/tests/test_updated.py": 4},
        last_output={"backend/tests/test_updated.py": "AssertionError: 1 != 2"},
    )
    drop_red_tests(tmp_path, record)
    assert (tmp_path / "backend/tests/test_updated.py").read_text() == "original"
    assert not (tmp_path / "backend/tests/test_created.py").exists()
    assert (tmp_path / "backend/tests/test_green.py").read_text() == "agent version"
    assert record.files_written == {"backend/tests/test_green.py": "create"}
    assert record.dropped == [
        {"path": "backend/tests/test_updated.py", "action": "update",
         "reason": "still failing after the repair budget was spent", "last_output": "AssertionError: 1 != 2"},
        {"path": "backend/tests/test_created.py", "action": "create", "reason": "never run", "last_output": ""},
    ]


def test_read_coverage_parses_both_formats(tmp_path):
    (tmp_path / "coverage.json").write_text(json.dumps({"totals": {"percent_covered": 42.424242}}))
    (tmp_path / "coverage-summary.json").write_text(json.dumps({"total": {"lines": {"pct": 47.68}}}))
    assert read_coverage("backend", tmp_path) == 42.42
    assert read_coverage("frontend", tmp_path) == 47.68


def test_read_coverage_tolerates_missing_reports(tmp_path):
    assert read_coverage("backend", tmp_path) is None


def test_suite_timeout_is_a_failure(tmp_path, monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1)
    monkeypatch.setattr(subprocess, "run", timeout)
    result = run_suite(tmp_path, "backend")
    assert (result.passed, result.coverage) == (False, None)
    assert "timed out" in result.output
