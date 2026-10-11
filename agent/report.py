"""Build the run report from recorded facts."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from agent.runtime import RunResult
from agent.tools import RunRecord
from agent.triage import Triage


def build_report(mode: str, model: str, triage: Triage, record: RunRecord | None, result: RunResult | None) -> dict:
    if not triage.targets:
        status = "nothing_to_do"
    elif result is None:
        status = "error"
    else:
        status = "ok" if result.stop_reason == "completed" else "incomplete"
    record = record or RunRecord()
    return {
        "version": 1,
        "mode": mode,
        "model": model,
        "status": status,
        "stop_reason": result.stop_reason if result else None,
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
        "test_runs": [asdict(r) for r in record.test_runs],
        "usage": asdict(result.usage) if result else None,
        "summary": result.summary if result else "",
    }


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
