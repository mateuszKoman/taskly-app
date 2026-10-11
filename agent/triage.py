"""Deterministic triage: which changed files are worth the model's attention."""

from __future__ import annotations

import subprocess
import tomllib
from dataclasses import asdict, dataclass, field
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath


@dataclass
class Target:
    path: str
    side: str
    status: str
    test_file: str
    test_exists: bool


@dataclass
class Ignored:
    path: str
    reason: str


@dataclass
class Triage:
    base: str
    merge_base: str
    targets: list[Target] = field(default_factory=list)
    ignored: list[Ignored] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def target(self, path: str) -> Target | None:
        return next((t for t in self.targets if t.path == path), None)


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout


def changed_files(root: Path, merge_base: str) -> list[tuple[str, str]]:
    """(status, path) for tracked changes since `merge_base` plus untracked files.

    Diffing against the working tree makes local runs see uncommitted work; in CI the
    working tree equals HEAD, so the result is the PR diff.
    """
    out = git(root, "diff", "--name-status", "--find-renames", "-z", merge_base)
    tokens = [t for t in out.split("\x00") if t]
    changes, i = [], 0
    while i < len(tokens):
        status = tokens[i][0]
        if status in "RC":
            changes.append(("A" if status == "C" else "M", tokens[i + 2]))
            i += 3
        else:
            changes.append((status, tokens[i + 1]))
            i += 2
    untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z")
    changes += [("A", p) for p in untracked.split("\x00") if p]
    return changes


def backend_omit_patterns(root: Path) -> list[str]:
    pyproject = root / "backend" / "pyproject.toml"
    if not pyproject.exists():
        return []
    config = tomllib.loads(pyproject.read_text())
    return config.get("tool", {}).get("coverage", {}).get("run", {}).get("omit", [])


def backend_test_file(path: str) -> str:
    # backend/app/features/todos/router.py -> backend/tests/features/todos/test_router.py
    rel = PurePosixPath(path).relative_to("backend/app")
    return str(PurePosixPath("backend/tests") / rel.parent / f"test_{rel.name}")


def classify(root: Path, status: str, path: str, omit: list[str]) -> Target | Ignored:
    if status == "D":
        return Ignored(path, "deleted")
    if path.startswith("agent/"):
        return Ignored(path, "agent code is excluded from its own runs")
    if path.startswith("backend/tests/"):
        return Ignored(path, "test file")
    if path.startswith("backend/app/") and path.endswith(".py"):
        if any(fnmatch(path, pattern) for pattern in omit):
            return Ignored(path, "excluded by backend coverage config")
        test_file = backend_test_file(path)
        return Target(path, "backend", status, test_file, (root / test_file).exists())
    if path.startswith("frontend/src/"):
        return Ignored(path, "frontend support is not enabled yet")
    return Ignored(path, "not application source")


def triage(root: Path, base: str) -> Triage:
    merge_base = git(root, "merge-base", base, "HEAD").strip()
    omit = backend_omit_patterns(root)
    result = Triage(base=base, merge_base=merge_base)
    for status, path in sorted(set(changed_files(root, merge_base)), key=lambda c: c[1]):
        item = classify(root, status, path, omit)
        (result.targets if isinstance(item, Target) else result.ignored).append(item)
    return result
