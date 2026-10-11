"""Build the run report from recorded facts."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from agent.runtime import RunResult
from agent.tools import RunRecord
from agent.triage import Triage
from agent.verify import SuiteResult


def suite_dict(result: SuiteResult) -> dict:
    data = asdict(result)
    data.pop("files", None)  # per-file detail is for target selection, not for the PR report
    return data


def run_status(triage: Triage, result: RunResult | None, error: str | None) -> str:
    if not triage.targets:
        return "nothing_to_do"
    if error or result is None:
        return "error"
    if result.stop_reason == "completed":
        return "ok"
    if result.stop_reason.startswith("limit:"):
        return "partial"
    return "incomplete"


def build_report(
    mode: str,
    model: str,
    triage: Triage,
    record: RunRecord | None = None,
    result: RunResult | None = None,
    suites: dict[str, dict[str, SuiteResult]] | None = None,
    error: str | None = None,
) -> dict:
    record = record or RunRecord()
    suites = suites or {}
    status = run_status(triage, result, error)
    suite_failed = any(not s["after"].passed for s in suites.values() if "after" in s)
    stop_reason = result.stop_reason if result else None
    return {
        "version": 1,
        "mode": mode,
        "model": model,
        "status": status,
        "stop_reason": stop_reason,
        "limit_hit": stop_reason.removeprefix("limit:") if stop_reason and stop_reason.startswith("limit:") else None,
        "error": error,
        "check_failed": status == "error" or suite_failed,
        "base": triage.base,
        "merge_base": triage.merge_base,
        "decisions": [record.decisions.get(t.path) or {
            "path": t.path, "side": t.side, "action": None, "reason": "no decision recorded",
            "test_file": t.test_file,
        } for t in triage.targets],
        "ignored": [asdict(i) for i in triage.ignored],
        "skills_loaded": record.skills_loaded,
        "files_written": [
            {"path": path, "action": action, "passed": record.last_result.get(path)}
            for path, action in record.files_written.items()
        ],
        "dropped": record.dropped,
        "suspected_bugs": record.suspected_bugs,
        "suites": {side: {phase: suite_dict(r) for phase, r in phases.items()} for side, phases in suites.items()},
        "test_runs": [asdict(r) for r in record.test_runs],
        "usage": asdict(result.usage) if result else None,
        "summary": result.summary if result else "",
    }


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
