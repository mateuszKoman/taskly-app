"""Deterministic triage: which changed files are worth the model's attention."""

from __future__ import annotations

import re
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
    coverage: float | None = None  # full mode only
    missing_lines: list[int] = field(default_factory=list)  # full mode only


@dataclass
class Ignored:
    path: str
    reason: str


@dataclass
class Triage:
    base: str
    merge_base: str
    mode: str = "pr"
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


def glob_regex(pattern: str) -> re.Pattern:
    """Compile a coverage glob (`**`, `*`, `?`, `{a,b}`) to an anchored regex."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        elif pattern[i] == "{" and "}" in pattern[i:]:
            end = pattern.index("}", i)
            out += "(?:" + "|".join(re.escape(a) for a in pattern[i + 1 : end].split(",")) + ")"
            i = end + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(f"^{out}$")


@dataclass
class FrontendCoverage:
    include: list[re.Pattern]
    exclude: list[re.Pattern]

    def covers(self, rel: str) -> bool:
        included = not self.include or any(p.match(rel) for p in self.include)
        return included and not any(p.match(rel) for p in self.exclude)


def frontend_coverage(root: Path) -> FrontendCoverage:
    """Read coverage include/exclude globs from vite.config.ts, the frontend's source of truth."""
    config = root / "frontend" / "vite.config.ts"
    text = config.read_text() if config.exists() else ""
    block = re.search(r"coverage\s*:\s*\{(.*?)\n\s*\}", text, re.S)
    body = block.group(1) if block else ""

    def globs(key: str) -> list[re.Pattern]:
        found = re.search(rf"\b{key}\s*:\s*\[(.*?)\]", body, re.S)
        return [glob_regex(g) for g in re.findall(r"['\"]([^'\"]+)['\"]", found.group(1))] if found else []

    return FrontendCoverage(globs("include"), globs("exclude"))


def frontend_test_file(root: Path, path: str) -> str:
    # frontend/src/lib/http.ts -> frontend/src/lib/http.test.ts, co-located; reuse an existing .ts/.tsx twin
    stem, suffix = path.rsplit(".", 1)
    for candidate in (f"{stem}.test.{suffix}", f"{stem}.test.{'tsx' if suffix == 'ts' else 'ts'}"):
        if (root / candidate).exists():
            return candidate
    return f"{stem}.test.{suffix}"


def backend_test_file(path: str) -> str:
    # backend/app/features/todos/router.py -> backend/tests/features/todos/test_router.py
    rel = PurePosixPath(path).relative_to("backend/app")
    return str(PurePosixPath("backend/tests") / rel.parent / f"test_{rel.name}")


def classify(root: Path, status: str, path: str, omit: list[str], frontend: FrontendCoverage) -> Target | Ignored:
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
        if re.search(r"\.test\.tsx?$", path):
            return Ignored(path, "test file")
        if not re.search(r"\.tsx?$", path):
            return Ignored(path, "not TypeScript source")
        if not frontend.covers(path.removeprefix("frontend/")):
            return Ignored(path, "excluded by frontend coverage config")
        test_file = frontend_test_file(root, path)
        return Target(path, "frontend", status, test_file, (root / test_file).exists())
    return Ignored(path, "not application source")


def triage(root: Path, base: str) -> Triage:
    merge_base = git(root, "merge-base", base, "HEAD").strip()
    omit = backend_omit_patterns(root)
    frontend = frontend_coverage(root)
    result = Triage(base=base, merge_base=merge_base)
    for status, path in sorted(set(changed_files(root, merge_base)), key=lambda c: c[1]):
        item = classify(root, status, path, omit, frontend)
        (result.targets if isinstance(item, Target) else result.ignored).append(item)
    return result
