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
SECRET_ENV = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)|^(ANTHROPIC_|GITHUB_|ACTIONS_)", re.I)


class ToolError(Exception):
    """A tool refused or failed. The message is returned to the model as an error result."""


@dataclass
class TestRun:
    target: str
    paths: list[str]
    exit_code: int
    passed: bool


@dataclass
class RunRecord:
    """Facts gathered while the agent works; the report is built from these, not from model prose."""

    decisions: dict[str, dict] = field(default_factory=dict)
    files_written: dict[str, str] = field(default_factory=dict)  # path -> "create" | "update"
    last_result: dict[str, bool] = field(default_factory=dict)  # test path -> passed in latest run
    test_runs: list[TestRun] = field(default_factory=list)
    skills_loaded: list[str] = field(default_factory=list)


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
        "description": "Run the given test files with the side's fixed test command and return the result.",
        "input_schema": obj(
            {
                "target": {"type": "string", "enum": ["backend"]},
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
        if rel not in self.record.files_written:
            self.record.files_written[rel] = "update" if resolved.exists() else "create"
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content)
        self.record.last_result.pop(rel, None)
        return f"wrote {rel} ({len(content)} characters)"

    def run_tests(self, target: str, paths: list[str]) -> str:
        if target != "backend":
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
        command = [
            backend_python(self.root), "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider",
            *(str(PurePosixPath(r).relative_to("backend")) for r in rels),
        ]
        try:
            proc = subprocess.run(
                command, cwd=self.root / "backend", env=safe_env(), capture_output=True,
                text=True, timeout=TEST_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            for rel in rels:
                self.record.last_result[rel] = False
            raise ToolError(f"tests timed out after {TEST_TIMEOUT_SECONDS}s") from None
        passed = proc.returncode == 0
        self.record.test_runs.append(TestRun(target, rels, proc.returncode, passed))
        for rel in rels:
            self.record.last_result[rel] = passed
        verdict = "PASSED" if passed else f"FAILED (exit code {proc.returncode})"
        return f"{verdict}\n{clip(proc.stdout + proc.stderr, MAX_TEST_OUTPUT_CHARS)}"

    def load_skill(self, name: str) -> str:
        skill = self.skills.get(name)
        if skill is None:
            raise ToolError(f"unknown skill {name!r}; available: {', '.join(self.skills)}")
        if name not in self.record.skills_loaded:
            self.record.skills_loaded.append(name)
        return skill.body

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
