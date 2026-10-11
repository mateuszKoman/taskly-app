"""Patch validation for the publish job: only plain test-file edits may reach the PR branch.

The publish job runs this from the base branch checkout, so a PR cannot loosen the rules it is checked by.
"""

from __future__ import annotations

import re

from agent.policy import is_test_path

HEADER = re.compile(r"^diff --git a/(\S+) b/(\S+)$")
FORBIDDEN = (
    ("rename from", "renames are not allowed"),
    ("rename to", "renames are not allowed"),
    ("copy from", "copies are not allowed"),
    ("copy to", "copies are not allowed"),
    ("deleted file mode", "deletions are not allowed"),
    ("old mode", "mode changes are not allowed"),
    ("new mode", "mode changes are not allowed"),
    ("GIT binary patch", "binary content is not allowed"),
    ("Binary files", "binary content is not allowed"),
)


def patch_errors(text: str) -> list[str]:
    """Every reason the patch must not be applied; empty when it is a plain set of test-file edits."""
    errors, current, saw_header, in_hunk = [], None, False, False
    for line in text.splitlines():
        if line.startswith("diff --git "):
            saw_header, in_hunk = True, False
            match = HEADER.match(line)
            if not match:
                errors.append(f"unparseable header: {line[:200]}")
                current = None
                continue
            a, b = match.groups()
            current = b
            if a != b:
                errors.append(f"{b}: source and target paths differ")
            if not is_test_path(b):
                errors.append(f"{b}: not an allowed test path")
            continue
        if current is None:
            continue
        if line.startswith("@@"):
            in_hunk = True
        if in_hunk:  # hunk lines are file content; only extended headers carry metadata
            continue
        if line.startswith("new file mode ") and line != "new file mode 100644":
            errors.append(f"{current}: new files must be regular, non-executable files")
        for prefix, reason in FORBIDDEN:
            if line.startswith(prefix):
                errors.append(f"{current}: {reason}")
        if line.startswith(("--- ", "+++ ")):
            path = line[4:]
            if path != "/dev/null" and path[2:] != current:
                errors.append(f"{current}: file header names a different path ({path[:200]})")
    if text.strip() and not saw_header:
        errors.append("not a git diff")
    return errors


def path_errors(paths: list[str]) -> list[str]:
    return [f"{p}: not an allowed test path" for p in paths if p and not is_test_path(p)]
