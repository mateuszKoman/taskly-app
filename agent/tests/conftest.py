import subprocess
from pathlib import Path

import pytest


def run_git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def write(root: Path, rel: str, text: str = "x = 1\n") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


VITE_CONFIG = """export default defineConfig({
  test: {
    coverage: {
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/main.tsx',
        'src/**/*.test.{ts,tsx}',
        'src/**/types.ts',
      ],
    },
  },
})
"""


@pytest.fixture
def repo(tmp_path):
    """A tiny git repo shaped like Taskly, with one commit on `main`."""
    run_git(tmp_path, "init", "-q", "-b", "main")
    run_git(tmp_path, "config", "user.email", "test@example.com")
    run_git(tmp_path, "config", "user.name", "Test")
    write(tmp_path, "backend/pyproject.toml", '[tool.coverage.run]\nomit = ["*/app/**/schemas.py", "*/app/**/__init__.py"]\n')
    write(tmp_path, "backend/app/features/todos/router.py")
    write(tmp_path, "backend/tests/features/todos/test_router.py", "def test_ok():\n    assert True\n")
    write(tmp_path, "frontend/vite.config.ts", VITE_CONFIG)
    write(tmp_path, "frontend/src/lib/http.ts", "export const a = 1\n")
    write(tmp_path, "frontend/src/App.tsx", "export const App = () => null\n")
    write(tmp_path, "frontend/src/App.test.tsx", "it('renders', () => {})\n")
    write(tmp_path, "README.md", "hello\n")
    run_git(tmp_path, "add", ".")
    run_git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path
