"""Deterministic verification: full suites with coverage, and dropping tests that never went green."""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from agent.tools import RunRecord, backend_python, clip, safe_env

SUITE_TIMEOUT_SECONDS = 600
MAX_SUITE_OUTPUT_CHARS = 4_000
COVERAGE_METRIC = {"backend": "statements+branches", "frontend": "lines"}


@dataclass
class SuiteResult:
    passed: bool
    exit_code: int
    coverage: float | None
    metric: str
    output: str


def suite_command(root: Path, side: str, out: Path) -> tuple[list[str], dict[str, str]]:
    env = safe_env()
    if side == "backend":
        command = [
            backend_python(root), "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider",
            "--cov=app", f"--cov-report=json:{out / 'coverage.json'}",
        ]
    else:
        command = [
            str(root / "frontend" / "node_modules" / ".bin" / "vitest"), "run", "--coverage",
            "--coverage.reporter=json-summary", f"--coverage.reportsDirectory={out}",
        ]
        env.update(CI="1", FORCE_COLOR="0")
    return command, env


def read_coverage(side: str, out: Path) -> float | None:
    try:
        if side == "backend":
            return round(json.loads((out / "coverage.json").read_text())["totals"]["percent_covered"], 2)
        return round(json.loads((out / "coverage-summary.json").read_text())["total"]["lines"]["pct"], 2)
    except (OSError, KeyError, ValueError):
        return None


def run_suite(root: Path, side: str) -> SuiteResult:
    metric = COVERAGE_METRIC[side]
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        command, env = suite_command(root, side, out)
        try:
            proc = subprocess.run(
                command, cwd=root / side, env=env, capture_output=True, text=True, timeout=SUITE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return SuiteResult(False, -1, None, metric, f"suite timed out after {SUITE_TIMEOUT_SECONDS}s")
        except OSError as exc:
            return SuiteResult(False, -1, None, metric, f"suite could not start: {exc}")
        output = clip(proc.stdout + proc.stderr, MAX_SUITE_OUTPUT_CHARS)
        return SuiteResult(proc.returncode == 0, proc.returncode, read_coverage(side, out), metric, output)


def drop_reason(record: RunRecord, path: str) -> str:
    if record.budget_spent(path):
        return "still failing after the repair budget was spent"
    if record.failures.get(path):
        return "still failing when the run ended"
    return "never run"


def drop_red_tests(root: Path, record: RunRecord) -> None:
    """Undo every written test file that is not green in its latest run, keeping the run's output green-only."""
    for path in list(record.files_written):
        if record.last_result.get(path) is True:
            continue
        original = record.originals.get(path)
        target = root / path
        if original is None:
            target.unlink(missing_ok=True)
        else:
            target.write_text(original)
        record.dropped.append({
            "path": path,
            "action": record.files_written.pop(path),
            "reason": drop_reason(record, path),
            "last_output": record.last_output.get(path, ""),
        })
        record.last_result.pop(path, None)
