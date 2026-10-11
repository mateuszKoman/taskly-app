"""Command line entry point: `python -m agent {triage,pr,render}`."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from agent.pipeline import run_pr
from agent.render import render_markdown
from agent.report import write_json
from agent.runtime import Agent, Config
from agent.skills import load_skills, skill_index
from agent.tools import RunRecord, Toolbox
from agent.triage import triage

ROOT = Path(__file__).resolve().parent.parent
AGENT_MD = Path(__file__).parent / "AGENT.md"


def system_prompt(skills) -> str:
    return f"{AGENT_MD.read_text().strip()}\n\n## Skills\n\nLoad a skill with `load_skill` when its description applies.\n\n{skill_index(skills)}\n"


def actions_run_url() -> str | None:
    server, repo, run_id = (os.environ.get(k) for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    return f"{server}/{repo}/actions/runs/{run_id}" if server and repo and run_id else None


def cmd_triage(args: argparse.Namespace) -> int:
    result = triage(ROOT, args.base)
    write_json(args.output_dir / "triage.json", result.to_dict())
    print(f"triage: {len(result.targets)} target(s), {len(result.ignored)} ignored")
    return 0


def cmd_pr(args: argparse.Namespace) -> int:
    result_triage = triage(ROOT, args.base)
    write_json(args.output_dir / "triage.json", result_triage.to_dict())
    print(f"triage: {len(result_triage.targets)} target(s), {len(result_triage.ignored)} ignored")

    config = Config(model=os.environ.get("AGENT_MODEL", Config.model))
    skills = load_skills()
    system = system_prompt(skills)

    def make_agent(record: RunRecord) -> Agent:
        import anthropic  # deferred: triage and nothing-to-do runs work without the SDK

        client = anthropic.Anthropic(max_retries=4).beta.messages
        return Agent(client, config, system, Toolbox(ROOT, result_triage, skills, record))

    report = run_pr(ROOT, result_triage, config.model, make_agent)
    write_json(args.output_dir / "report.json", report)
    (args.output_dir / "summary.md").write_text(render_markdown(report, actions_run_url()))
    usage = report["usage"] or {}
    print(f"status: {report['status']}, turns: {usage.get('turns', 0)}, check_failed: {report['check_failed']}")
    return 1 if report["check_failed"] else 0


def cmd_render(args: argparse.Namespace) -> int:
    report = json.loads(args.report.read_text())
    sys.stdout.write(render_markdown(report, args.run_url or actions_run_url()))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agent")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, handler, help_text in (
        ("triage", cmd_triage, "classify the change without calling the model"),
        ("pr", cmd_pr, "run the agent on the change and write report.json and summary.md"),
    ):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("--base", required=True, help="base ref of the change, e.g. origin/main")
        sub.add_argument("--output-dir", type=Path, default=ROOT / "agent-output")
        sub.set_defaults(handler=handler)
    render = commands.add_parser("render", help="render a report.json as Markdown on stdout")
    render.add_argument("--report", type=Path, default=ROOT / "agent-output" / "report.json")
    render.add_argument("--run-url", help="link to the workflow run")
    render.set_defaults(handler=cmd_render)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
