"""The agent's tool set. Every filesystem path passes through PathPolicy; no shell."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from agent.policy import HIDDEN_DIRS, TEST_PATTERNS, PathPolicy, PolicyError
from agent.skills import Skill
from agent.triage import Triage, git

MAX_READ_CHARS = 60_000
MAX_LIST_ENTRIES = 500
MAX_TEST_OUTPUT_CHARS = 12_000
TEST_TIMEOUT_SECONDS = 300
MAX_REPAIRS = 3  # failed runs a test file may be repaired after; one more failure spends its budget
MAX_FAILURE_EXCERPT_CHARS = 2_000
SECRET_ENV = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)|^(ANTHROPIC_|GITHUB_|ACTIONS_)", re.I)


class ToolError(Exception):
    """A tool refused or failed. The message is returned to the model as an error result."""


@dataclass
class TestRun:
    target: str
    path: str
    exit_code: int
    passed: bool


@dataclass
class RunRecord:
    """Facts gathered while the agent works; the report is built from these, not from model prose."""

    decisions: dict[str, dict] = field(default_factory=dict)
    files_written: dict[str, str] = field(default_factory=dict)  # path -> "create" | "update"
    originals: dict[str, str | None] = field(default_factory=dict)  # content before the first write
    last_result: dict[str, bool] = field(default_factory=dict)  # test path -> passed in latest run
    last_output: dict[str, str] = field(default_factory=dict)  # test path -> excerpt of latest failure
    failures: dict[str, int] = field(default_factory=dict)  # test path -> failed runs
    test_runs: list[TestRun] = field(default_factory=list)
    skills_loaded: list[str] = field(default_factory=list)
    suspected_bugs: list[dict] = field(default_factory=list)
    dropped: list[dict] = field(default_factory=list)

    def budget_spent(self, path: str) -> bool:
        return self.failures.get(path, 0) > MAX_REPAIRS


def clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"[... {len(text) - limit} characters truncated ...]\n" + text[-limit:]


def safe_env() -> dict[str, str]:
    """Environment for test subprocesses: the PR's code runs here, so secrets stay out."""
    return {k: v for k, v in os.environ.items() if not SECRET_ENV.search(k)}


def backend_python(root: Path) -> str:
    override = os.environ.get("AGENT_BACKEND_PYTHON")
    if override:
        return override
    venv = root / "backend" / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def frontend_bin(root: Path, name: str) -> Path:
    return root / "frontend" / "node_modules" / ".bin" / name


def run_quiet(command: list[str], cwd: Path, env: dict[str, str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=TEST_TIMEOUT_SECONDS)
        return proc.returncode, proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        return -1, f"timed out after {TEST_TIMEOUT_SECONDS}s"


def obj(properties: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


STR = {"type": "string"}

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "list_files",
        "description": "List the entries of one repository directory (non-recursive). Directories end with '/'.",
        "input_schema": obj({"path": {**STR, "description": "Repo-relative directory, '.' for the root."}}, ["path"]),
    },
    {
        "name": "read_file",
        "description": "Read a repository text file. Secrets files and dependency/build directories are refused.",
        "input_schema": obj({"path": {**STR, "description": "Repo-relative file path."}}, ["path"]),
    },
    {
        "name": "git_diff",
        "description": "Show the change to one file since the merge base. New files are shown in full.",
        "input_schema": obj({"path": {**STR, "description": "Repo-relative file path from the triage."}}, ["path"]),
    },
    {
        "name": "write_test_file",
        "description": (
            "Create or overwrite a test file with the full file content. Only backend/tests/**/test_*.py "
            "and frontend/src/**/*.test.ts(x) are writable."
        ),
        "input_schema": obj({"path": STR, "content": {**STR, "description": "Complete file content."}}, ["path", "content"]),
    },
    {
        "name": "run_tests",
        "description": (
            "Run the given test files, each on its own, with the side's fixed command "
            "(backend: pytest, frontend: vitest run) and return each result."
        ),
        "input_schema": obj(
            {
                "target": {"type": "string", "enum": ["backend", "frontend"]},
                "paths": {"type": "array", "items": STR, "description": "Repo-relative test file paths."},
            },
            ["target", "paths"],
        ),
    },
    {
        "name": "load_skill",
        "description": "Load the full instructions of a skill listed in the system prompt.",
        "input_schema": obj({"name": STR}, ["name"]),
    },
    {
        "name": "flag_suspected_bug",
        "description": (
            "Report a test case you removed because the source behaviour itself looks wrong. "
            "Say what you expected and what the code does."
        ),
        "input_schema": obj(
            {
                "test_file": {**STR, "description": "The test file the case was removed from."},
                "test_name": {**STR, "description": "Name of the removed test case."},
                "reason": {**STR, "description": "Expected versus actual behaviour, one or two sentences."},
            },
            ["test_file", "test_name", "reason"],
        ),
    },
    {
        "name": "record_decision",
        "description": "Record the decision for one triage target: create, update or skip, with a one-sentence reason.",
        "input_schema": obj(
            {
                "path": {**STR, "description": "The target's source path, exactly as in the triage."},
                "action": {"type": "string", "enum": ["create", "update", "skip"]},
                "reason": STR,
            },
            ["path", "action", "reason"],
        ),
    },
]

for spec in TOOL_SPECS:
    spec["strict"] = True


class Toolbox:
    def __init__(self, root: Path, triage: Triage, skills: dict[str, Skill], record: RunRecord):
        self.root = root.resolve()
        self.policy = PathPolicy(self.root)
        self.triage = triage
        self.skills = skills
        self.record = record
        self.handlers: dict[str, Callable[..., str]] = {
            "list_files": self.list_files,
            "read_file": self.read_file,
            "git_diff": self.git_diff,
            "write_test_file": self.write_test_file,
            "run_tests": self.run_tests,
            "load_skill": self.load_skill,
            "record_decision": self.record_decision,
            "flag_suspected_bug": self.flag_suspected_bug,
        }

    @property
    def specs(self) -> list[dict[str, Any]]:
        return TOOL_SPECS

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        handler = self.handlers.get(name)
        if handler is None:
            raise ToolError(f"unknown tool {name!r}")
        try:
            return handler(**arguments)
        except PolicyError as exc:
            raise ToolError(str(exc)) from exc
        except TypeError as exc:
            raise ToolError(f"bad arguments for {name}: {exc}") from exc

    def list_files(self, path: str) -> str:
        rel, resolved = self.policy.readable(path)
        if not resolved.is_dir():
            raise ToolError(f"{rel} is not a directory")
        entries = []
        for child in sorted(resolved.iterdir()):
            if child.name in HIDDEN_DIRS or child.is_symlink():
                continue
            entries.append(child.name + ("/" if child.is_dir() else ""))
        return "\n".join(entries[:MAX_LIST_ENTRIES]) or "(empty)"

    def read_file(self, path: str) -> str:
        rel, resolved = self.policy.readable(path)
        if not resolved.is_file():
            raise ToolError(f"{rel} is not a file")
        try:
            text = resolved.read_text()
        except UnicodeDecodeError:
            raise ToolError(f"{rel} is not a text file") from None
        return clip(text, MAX_READ_CHARS)

    def git_diff(self, path: str) -> str:
        rel, resolved = self.policy.readable(path)
        diff = git(self.root, "diff", self.triage.merge_base, "--", rel)
        if not diff and resolved.is_file():
            return f"(new untracked file)\n{clip(resolved.read_text(), MAX_READ_CHARS)}"
        return clip(diff, MAX_READ_CHARS) or "(no changes)"

    def write_test_file(self, path: str, content: str) -> str:
        rel, resolved = self.policy.writable_test(path)
        if self.record.budget_spent(rel):
            raise ToolError(
                f"{rel} has failed {self.record.failures[rel]} runs and its repair budget is spent; "
                "it will be dropped from the output. Flag any suspected bug and move on."
            )
        if rel not in self.record.files_written:
            existed = resolved.exists()
            self.record.files_written[rel] = "update" if existed else "create"
            self.record.originals[rel] = resolved.read_text() if existed else None
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content)
        self.record.last_result.pop(rel, None)
        self.format_frontend(rel)
        return f"wrote {rel} ({len(content)} characters)"

    def format_frontend(self, rel: str) -> None:
        """Apply the repo's Prettier style so generated tests match hand-written ones; a parse error is left for the run."""
        prettier = frontend_bin(self.root, "prettier")
        if rel.startswith("frontend/") and prettier.exists():
            run_quiet([str(prettier), "--write", "--log-level", "silent", rel.removeprefix("frontend/")],
                      self.root / "frontend", safe_env())

    def typecheck_frontend(self, rel: str) -> tuple[int, str]:
        """Vitest strips types without checking them; tsc catches what `npm run build` would reject."""
        tsc = frontend_bin(self.root, "tsc")
        if not tsc.exists():
            return 0, ""
        code, output = run_quiet([str(tsc), "--noEmit", "--pretty", "false", "-p", "."], self.root / "frontend", safe_env())
        side_path = rel.removeprefix("frontend/")
        errors = [line for line in output.splitlines() if line.startswith(f"{side_path}(")]
        return (1, "Type errors (tsc --noEmit):\n" + "\n".join(errors)) if errors else (0, "")

    def test_command(self, target: str, rel: str) -> tuple[list[str], Path, dict[str, str]]:
        side_dir = self.root / target
        side_path = str(PurePosixPath(rel).relative_to(target))
        env = safe_env()
        if target == "backend":
            command = [backend_python(self.root), "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"]
        else:
            vitest = side_dir / "node_modules" / ".bin" / "vitest"
            if not vitest.exists():
                raise ToolError("frontend dependencies are not installed (run `npm ci` in frontend/)")
            command = [str(vitest), "run"]
            env.update(CI="1", FORCE_COLOR="0")
        return [*command, side_path], side_dir, env

    def run_tests(self, target: str, paths: list[str]) -> str:
        if target not in TEST_PATTERNS:
            raise ToolError(f"unsupported test target {target!r}")
        if not paths:
            raise ToolError("paths must list at least one test file")
        rels = []
        for path in paths:
            rel, resolved = self.policy.resolve(path)
            if not TEST_PATTERNS[target].match(rel):
                raise ToolError(f"{rel} is not a {target} test file")
            if not resolved.is_file():
                raise ToolError(f"{rel} does not exist")
            rels.append(rel)
        return "\n\n".join(self.run_one(target, rel) for rel in rels)

    def run_one(self, target: str, rel: str) -> str:
        command, cwd, env = self.test_command(target, rel)
        exit_code, output = run_quiet(command, cwd, env)
        if exit_code == 0 and target == "frontend":
            exit_code, output = self.typecheck_frontend(rel)
        passed = exit_code == 0
        self.record.test_runs.append(TestRun(target, rel, exit_code, passed))
        self.record.last_result[rel] = passed
        if passed:
            return f"== {rel}: PASSED"
        self.record.failures[rel] = self.record.failures.get(rel, 0) + 1
        self.record.last_output[rel] = clip(output, MAX_FAILURE_EXCERPT_CHARS)
        left = MAX_REPAIRS - self.record.failures[rel] + 1
        budget = f"{left} repair(s) left" if left > 0 else "repair budget spent; this file will be dropped"
        return f"== {rel}: FAILED (exit code {exit_code}, {budget})\n{clip(output, MAX_TEST_OUTPUT_CHARS)}"

    def load_skill(self, name: str) -> str:
        skill = self.skills.get(name)
        if skill is None:
            raise ToolError(f"unknown skill {name!r}; available: {', '.join(self.skills)}")
        if name not in self.record.skills_loaded:
            self.record.skills_loaded.append(name)
        return skill.body

    def flag_suspected_bug(self, test_file: str, test_name: str, reason: str) -> str:
        rel = self.policy.writable_test(test_file)[0]
        if not test_name.strip() or not reason.strip():
            raise ToolError("test_name and reason must not be empty")
        self.record.suspected_bugs.append({"test_file": rel, "test_name": test_name.strip(), "reason": reason.strip()})
        return f"flagged suspected bug from {rel}::{test_name.strip()}"

    def record_decision(self, path: str, action: str, reason: str) -> str:
        target = self.triage.target(path)
        if target is None:
            raise ToolError(f"{path!r} is not a triage target")
        if action not in ("create", "update", "skip"):
            raise ToolError(f"invalid action {action!r}")
        if not reason.strip():
            raise ToolError("reason must not be empty")
        self.record.decisions[path] = {
            "path": path, "side": target.side, "action": action,
            "reason": reason.strip(), "test_file": target.test_file,
        }
        return f"recorded {action} for {path}"
