import subprocess

import pytest

from agent.patch import patch_errors, path_errors
from agent.tests.conftest import run_git, write


def diff(repo):
    """The diff the workflow collects: untracked files marked intent-to-add, tracked edits as they are."""
    untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=repo,
                               check=True, capture_output=True, text=True).stdout.split()
    if untracked:
        run_git(repo, "add", "--intent-to-add", "--", *untracked)
    return subprocess.run(["git", "diff", "--binary"], cwd=repo, check=True, capture_output=True, text=True).stdout


def test_new_and_updated_test_files_pass(repo):
    write(repo, "backend/tests/core/test_new.py", "def test_new():\n    pass\n")
    write(repo, "backend/tests/features/todos/test_router.py", "def test_ok():\n    assert 1\n")
    write(repo, "frontend/src/lib/http.test.ts", "it('works', () => {})\n")
    assert patch_errors(diff(repo)) == []


def test_source_change_is_rejected(repo):
    write(repo, "backend/app/features/todos/router.py", "x = 'pwned'\n")
    assert patch_errors(diff(repo)) == ["backend/app/features/todos/router.py: not an allowed test path"]


def test_workflow_change_is_rejected(repo):
    write(repo, ".github/workflows/test_evil.py", "x = 1\n")
    assert patch_errors(diff(repo)) == [".github/workflows/test_evil.py: not an allowed test path"]


def test_deletion_is_rejected(repo):
    (repo / "backend/tests/features/todos/test_router.py").unlink()
    assert "deletions are not allowed" in patch_errors(diff(repo))[0]


def test_executable_and_symlink_files_are_rejected(repo):
    write(repo, "backend/tests/test_exec.py", "x = 1\n")
    (repo / "backend/tests/test_exec.py").chmod(0o755)
    (repo / "backend/tests/test_link.py").symlink_to("/etc/passwd")
    errors = patch_errors(diff(repo))
    assert "backend/tests/test_exec.py: new files must be regular, non-executable files" in errors
    assert "backend/tests/test_link.py: new files must be regular, non-executable files" in errors


def test_mode_change_and_binary_are_rejected(repo):
    (repo / "backend/tests/features/todos/test_router.py").chmod(0o755)
    write(repo, "backend/tests/test_blob.py", "")
    (repo / "backend/tests/test_blob.py").write_bytes(b"\x00\x01\x02binary")
    errors = patch_errors(diff(repo))
    assert any("mode changes are not allowed" in e for e in errors)
    assert any("binary content is not allowed" in e for e in errors)


def test_rename_is_rejected():
    patch = (
        "diff --git a/backend/tests/test_a.py b/backend/tests/test_b.py\n"
        "similarity index 100%\nrename from backend/tests/test_a.py\nrename to backend/tests/test_b.py\n"
    )
    errors = patch_errors(patch)
    assert "backend/tests/test_b.py: source and target paths differ" in errors
    assert "backend/tests/test_b.py: renames are not allowed" in errors


def test_mismatched_file_header_is_rejected():
    patch = (
        "diff --git a/backend/tests/test_a.py b/backend/tests/test_a.py\n"
        "--- a/backend/tests/test_a.py\n+++ b/backend/app/main.py\n@@ -1 +1 @@\n-x\n+y\n"
    )
    assert patch_errors(patch) == ["backend/tests/test_a.py: file header names a different path (b/backend/app/main.py)"]


def test_hunk_content_that_looks_like_headers_is_fine():
    patch = (
        "diff --git a/backend/tests/test_a.py b/backend/tests/test_a.py\n"
        "--- a/backend/tests/test_a.py\n+++ b/backend/tests/test_a.py\n@@ -1,2 +1,2 @@\n"
        "--- old comment\n+++ new comment\n-old mode\n+new mode 100755\n"
    )
    assert patch_errors(patch) == []


@pytest.mark.parametrize("text, expected", [("", []), ("random text\n", ["not a git diff"])])
def test_empty_and_garbage_input(text, expected):
    assert patch_errors(text) == expected


def test_path_errors():
    assert path_errors(["backend/tests/test_a.py", "", "frontend/src/main.tsx"]) == [
        "frontend/src/main.tsx: not an allowed test path",
    ]
