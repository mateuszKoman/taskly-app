"""Full mode: targets come from coverage gaps across the repo instead of a PR diff."""

from __future__ import annotations

from pathlib import Path

from agent.triage import Ignored, Target, Triage, backend_test_file, frontend_test_file, git
from agent.verify import SuiteResult

DEFAULT_THRESHOLD = 90.0
DEFAULT_MAX_TARGETS = 8


def test_file_for(root: Path, side: str, path: str) -> str:
    return backend_test_file(path) if side == "backend" else frontend_test_file(root, path)


def full_triage(
    root: Path,
    suites: dict[str, SuiteResult],
    threshold: float = DEFAULT_THRESHOLD,
    max_targets: int = DEFAULT_MAX_TARGETS,
) -> Triage:
    """The files with the most uncovered lines below `threshold`, at most `max_targets` of them.

    Coverage reports already honour each side's include/exclude config, so every file in them is in scope.
    """
    head = git(root, "rev-parse", "HEAD").strip()
    result = Triage(base="(full)", merge_base=head, mode="full")
    gaps = []
    for side, suite in sorted(suites.items()):
        for f in suite.files:
            if f.coverage < threshold and f.missing_lines:
                gaps.append((side, f))
            else:
                result.ignored.append(Ignored(f.path, f"coverage {f.coverage:.2f}% meets the {threshold:g}% threshold"))
    gaps.sort(key=lambda gap: (-len(gap[1].missing_lines), gap[1].path))
    for side, f in gaps[:max_targets]:
        test_file = test_file_for(root, side, f.path)
        result.targets.append(Target(
            f.path, side, "M", test_file, (root / test_file).exists(), f.coverage, f.missing_lines,
        ))
    for side, f in gaps[max_targets:]:
        result.ignored.append(Ignored(f.path, f"coverage {f.coverage:.2f}%, beyond this run's {max_targets}-target budget"))
    return result
