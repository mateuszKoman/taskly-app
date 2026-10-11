"""Path policy: the single gate between model-supplied paths and the filesystem."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

BACKEND_TEST_PATTERN = re.compile(r"^backend/tests/(?:[A-Za-z0-9_]+/)*test_[A-Za-z0-9_]+\.py$")
FRONTEND_TEST_PATTERN = re.compile(r"^frontend/src/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.test\.tsx?$")
TEST_PATTERNS = {"backend": BACKEND_TEST_PATTERN, "frontend": FRONTEND_TEST_PATTERN}

# Directories that are never useful to the model and may hold secrets or huge trees.
HIDDEN_DIRS = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", "coverage", "dist"})
SECRET_NAME = re.compile(r"^(\.env(?!\.(example|sample)$)(\..*)?|.*\.(pem|key|p12|pfx)|id_rsa.*|\.npmrc|\.pypirc|\.netrc)$")


class PolicyError(ValueError):
    """A path was refused. The message is safe to show to the model."""


def normalize(path: str) -> str:
    """Return a clean repo-relative POSIX path, or raise PolicyError."""
    if not isinstance(path, str) or not path.strip():
        raise PolicyError("path must be a non-empty string")
    if "\x00" in path or "\\" in path:
        raise PolicyError(f"refused path {path!r}: illegal character")
    pure = PurePosixPath(path)
    if pure.is_absolute():
        raise PolicyError(f"refused path {path!r}: absolute paths are not allowed")
    parts = [p for p in pure.parts if p != "."]
    if ".." in parts:
        raise PolicyError(f"refused path {path!r}: '..' is not allowed")
    return "/".join(parts) or "."


def test_side(path: str) -> str | None:
    """Return 'backend' or 'frontend' when `path` is an allowed test-file path."""
    for side, pattern in TEST_PATTERNS.items():
        if pattern.match(path):
            return side
    return None


def is_test_path(path: str) -> bool:
    try:
        return test_side(normalize(path)) is not None
    except PolicyError:
        return False


class PathPolicy:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def resolve(self, path: str) -> tuple[str, Path]:
        """Normalize and resolve `path` inside the repo, refusing symlinks anywhere along it."""
        rel = normalize(path)
        current = self.root
        for part in PurePosixPath(rel).parts if rel != "." else ():
            current = current / part
            if current.is_symlink():
                raise PolicyError(f"refused path {path!r}: symlinks are not allowed")
        resolved = current.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise PolicyError(f"refused path {path!r}: outside the repository")
        return rel, resolved

    def readable(self, path: str) -> tuple[str, Path]:
        rel, resolved = self.resolve(path)
        parts = PurePosixPath(rel).parts
        if any(part in HIDDEN_DIRS for part in parts):
            raise PolicyError(f"refused path {path!r}: inside an excluded directory")
        if parts and SECRET_NAME.match(parts[-1]):
            raise PolicyError(f"refused path {path!r}: secrets files are never readable")
        return rel, resolved

    def writable_test(self, path: str) -> tuple[str, Path]:
        rel, resolved = self.resolve(path)
        if test_side(rel) is None:
            raise PolicyError(
                f"refused path {path!r}: writes are limited to backend/tests/**/test_*.py "
                "and frontend/src/**/*.test.ts(x)"
            )
        return rel, resolved
