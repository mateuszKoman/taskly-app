"""One PR run end to end: baseline suites, agent, drop red tests, final suites, report."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from agent.report import build_report
from agent.runtime import Agent
from agent.tools import RunRecord
from agent.triage import Triage
from agent.verify import SuiteResult, drop_red_tests, run_suite

log = logging.getLogger("agent")

SuiteRunner = Callable[[Path, str], SuiteResult]


def run_pr(
    root: Path,
    triage: Triage,
    model: str,
    make_agent: Callable[[RunRecord], Agent],
    suite_runner: SuiteRunner = run_suite,
) -> dict:
    if not triage.targets:
        return build_report("pr", model, triage)
    sides = sorted({t.side for t in triage.targets})
    suites = {side: {"before": suite_runner(root, side)} for side in sides}
    record = RunRecord()
    result, error = None, None
    try:
        result = make_agent(record).run(triage)
    except Exception as exc:  # API outage, bad config, tool bug: still clean up and report what happened
        log.exception("agent run failed")
        error = f"{type(exc).__name__}: {exc}"
    drop_red_tests(root, record)
    for side in sides:
        suites[side]["after"] = suite_runner(root, side)
    return build_report("pr", model, triage, record, result, suites, error)
