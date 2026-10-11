"""Command line entry point: `python -m agent {triage,pr} --base <ref>`."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from agent.report import build_report, write_json
from agent.runtime import Agent, Config
from agent.skills import load_skills, skill_index
from agent.tools import RunRecord, Toolbox
from agent.triage import triage

ROOT = Path(__file__).resolve().parent.parent
AGENT_MD = Path(__file__).parent / "AGENT.md"


def system_prompt(skills) -> str:
    return f"{AGENT_MD.read_text().strip()}\n\n## Skills\n\nLoad a skill with `load_skill` when its description applies.\n\n{skill_index(skills)}\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agent")
    parser.add_argument("command", choices=["triage", "pr"])
    parser.add_argument("--base", required=True, help="Base ref of the change, e.g. origin/main")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "agent-output")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    result_triage = triage(ROOT, args.base)
    write_json(args.output_dir / "triage.json", result_triage.to_dict())
    print(f"triage: {len(result_triage.targets)} target(s), {len(result_triage.ignored)} ignored")
    if args.command == "triage":
        return 0

    config = Config(model=os.environ.get("AGENT_MODEL", Config.model))
    if not result_triage.targets:
        write_json(args.output_dir / "report.json", build_report("pr", config.model, result_triage, None, None))
        print("nothing to test")
        return 0

    import anthropic  # deferred: triage and nothing-to-do runs work without the SDK

    skills = load_skills()
    record = RunRecord()
    toolbox = Toolbox(ROOT, result_triage, skills, record)
    agent = Agent(anthropic.Anthropic().beta.messages, config, system_prompt(skills), toolbox)
    result = None
    try:
        result = agent.run(result_triage)
    finally:
        report = build_report("pr", config.model, result_triage, record, result)
        write_json(args.output_dir / "report.json", report)
    print(f"status: {report['status']} ({result.stop_reason}), {result.usage.turns} turn(s)")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
