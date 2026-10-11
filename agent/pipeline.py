"""One PR run end to end: baseline suites, agent, drop red tests, final suites, report."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from agent.full import full_triage
from agent.report import build_report
from agent.runtime import Agent
from agent.tools import RunRecord
from agent.triage import Triage
from agent.verify import SuiteResult, drop_red_tests, run_suite

log = logging.getLogger("agent")

SuiteRunner = Callable[[Path, str], SuiteResult]
AgentFactory = Callable[[Triage, RunRecord], Agent]
SIDES = ("backend", "frontend")


def run_pr(
    root: Path,
    triage: Triage,
    model: str,
    make_agent: AgentFactory,
    suite_runner: SuiteRunner = run_suite,
) -> dict:
    if not triage.targets:
        return build_report("pr", model, triage)
    sides = sorted({t.side for t in triage.targets})
    suites = {side: {"before": suite_runner(root, side)} for side in sides}
    return finish(root, triage, model, make_agent, suite_runner, suites)


def run_full(
    root: Path,
    model: str,
    make_agent: AgentFactory,
    suite_runner: SuiteRunner = run_suite,
    threshold: float = 90.0,
    max_targets: int = 8,
) -> dict:
    """Close coverage gaps across the repo: the baseline suites double as target selection."""
    before = {side: suite_runner(root, side) for side in SIDES}
    triage = full_triage(root, before, threshold, max_targets)
    suites = {side: {"before": result} for side, result in before.items()}
    if not triage.targets:
        return build_report("full", model, triage, suites=suites)
    return finish(root, triage, model, make_agent, suite_runner, suites)


def finish(
    root: Path,
    triage: Triage,
    model: str,
    make_agent: AgentFactory,
    suite_runner: SuiteRunner,
    suites: dict[str, dict[str, SuiteResult]],
) -> dict:
    """Run the agent, drop red tests, rerun the suites, and report."""
    record = RunRecord()
    result, error = None, None
    try:
        result = make_agent(triage, record).run(triage)
    except Exception as exc:  # API outage, bad config, tool bug: still clean up and report what happened
        log.exception("agent run failed")
        error = f"{type(exc).__name__}: {exc}"
    drop_red_tests(root, record)
    for side in suites:
        suites[side]["after"] = suite_runner(root, side)
    return build_report(triage.mode, model, triage, record, result, suites, error)
