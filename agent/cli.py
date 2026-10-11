"""Command line entry point: `python -m agent {triage,pr,render}`."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from agent.patch import patch_errors, path_errors
from agent.full import DEFAULT_MAX_TARGETS, DEFAULT_THRESHOLD
from agent.pipeline import run_full, run_pr
from agent.render import render_markdown
from agent.report import write_json
from agent.runtime import Agent, Config
from agent.skills import load_skills, skill_index
from agent.tools import RunRecord, Toolbox
from agent.triage import Triage, triage

ROOT = Path(__file__).resolve().parent.parent
AGENT_MD = Path(__file__).parent / "AGENT.md"


def system_prompt(skills) -> str:
    return f"{AGENT_MD.read_text().strip()}\n\n## Skills\n\nLoad a skill with `load_skill` when its description applies.\n\n{skill_index(skills)}\n"


def actions_run_url() -> str | None:
    server, repo, run_id = (os.environ.get(k) for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    return f"{server}/{repo}/actions/runs/{run_id}" if server and repo and run_id else None


def agent_factory(config: Config):
    skills = load_skills()
    system = system_prompt(skills)

    def make_agent(run_triage: Triage, record: RunRecord) -> Agent:
        import anthropic  # deferred: triage and nothing-to-do runs work without the SDK

        client = anthropic.Anthropic(max_retries=4).beta.messages
        return Agent(client, config, system, Toolbox(ROOT, run_triage, skills, record))

    return make_agent


def write_outputs(output_dir: Path, report: dict) -> int:
    write_json(output_dir / "report.json", report)
    (output_dir / "summary.md").write_text(render_markdown(report, actions_run_url()))
    usage = report["usage"] or {}
    print(f"status: {report['status']}, turns: {usage.get('turns', 0)}, check_failed: {report['check_failed']}")
    for side, phases in report["suites"].items():
        before, after = phases.get("before", {}), phases.get("after", {})
        print(f"{side}: coverage {before.get('coverage')} -> {after.get('coverage', before.get('coverage'))}")
    return 1 if report["check_failed"] else 0


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
    report = run_pr(ROOT, result_triage, config.model, agent_factory(config))
    return write_outputs(args.output_dir, report)


def cmd_full(args: argparse.Namespace) -> int:
    # Several targets per run: a larger budget than a PR run, which is fine for a local, supervised run.
    config = Config(
        model=os.environ.get("AGENT_MODEL", Config.model),
        max_turns=args.max_turns, max_total_tokens=6_000_000, deadline_seconds=30 * 60,
    )
    report = run_full(ROOT, config.model, agent_factory(config),
                      threshold=args.threshold, max_targets=args.max_targets)
    return write_outputs(args.output_dir, report)


def cmd_render(args: argparse.Namespace) -> int:
    report = json.loads(args.report.read_text())
    sys.stdout.write(render_markdown(report, args.run_url or actions_run_url()))
    return 0


def report_errors(errors: list[str]) -> int:
    for error in errors:
        print(f"::error title=Patch rejected::{error}")
    return 1 if errors else 0


def cmd_validate_patch(args: argparse.Namespace) -> int:
    return report_errors(patch_errors(args.patch.read_text()))


def cmd_check_paths(args: argparse.Namespace) -> int:
    return report_errors(path_errors(sys.stdin.read().split("\0")))


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
    full = commands.add_parser("full", help="close coverage gaps across the repo (local use)")
    full.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="target files below this coverage %%")
    full.add_argument("--max-targets", type=int, default=DEFAULT_MAX_TARGETS, help="files to work on in one run")
    full.add_argument("--max-turns", type=int, default=80)
    full.add_argument("--output-dir", type=Path, default=ROOT / "agent-output")
    full.set_defaults(handler=cmd_full)
    render = commands.add_parser("render", help="render a report.json as Markdown on stdout")
    render.add_argument("--report", type=Path, default=ROOT / "agent-output" / "report.json")
    render.add_argument("--run-url", help="link to the workflow run")
    render.set_defaults(handler=cmd_render)
    validate = commands.add_parser("validate-patch", help="reject a patch that touches anything but test files")
    validate.add_argument("--patch", type=Path, required=True)
    validate.set_defaults(handler=cmd_validate_patch)
    check = commands.add_parser("check-paths", help="reject NUL-separated paths on stdin that are not test files")
    check.set_defaults(handler=cmd_check_paths)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
