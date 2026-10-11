import pytest

from agent.render import MARKER, MAX_COMMENT_CHARS, inline, render_markdown


def make_report(**overrides):
    report = {
        "version": 1, "mode": "pr", "model": "claude-sonnet-5-5", "status": "ok", "stop_reason": "completed",
        "limit_hit": None, "error": None, "check_failed": False, "base": "origin/main",
        "merge_base": "0123456789abcdef0123", "decisions": [], "ignored": [], "skills_loaded": [],
        "files_written": [], "dropped": [], "suspected_bugs": [], "suites": {}, "test_runs": [],
        "usage": {"turns": 7, "input_tokens": 12345, "output_tokens": 678, "cache_read_input_tokens": 90000},
        "summary": "",
    }
    report.update(overrides)
    return report


def suite(passed, coverage, metric="lines"):
    return {"passed": passed, "exit_code": 0 if passed else 1, "coverage": coverage, "metric": metric, "output": ""}


FULL = make_report(
    decisions=[
        {"path": "backend/app/features/todos/router.py", "side": "backend", "action": "update",
         "reason": "new due_soon filter has no test", "test_file": "backend/tests/features/todos/test_router.py"},
        {"path": "frontend/src/lib/http.ts", "side": "frontend", "action": "skip",
         "reason": "comment-only change", "test_file": "frontend/src/lib/http.test.ts"},
    ],
    files_written=[{"path": "backend/tests/features/todos/test_router.py", "action": "update", "passed": True}],
    dropped=[{"path": "frontend/src/App.test.tsx", "action": "create",
              "reason": "still failing after the repair budget was spent", "last_output": "AssertionError: 1 != 2"}],
    suspected_bugs=[{"test_file": "backend/tests/test_v.py", "test_name": "test_blank",
                     "reason": "is_blank returns True for non-empty input"}],
    suites={"backend": {"before": suite(True, 42.42, "statements+branches"), "after": suite(True, 48.1, "statements+branches")}},
    skills_loaded=["triage-changes", "write-backend-tests"],
    ignored=[{"path": "README.md", "reason": "not application source"}],
    summary="Pinned the due-soon filter.\nSkipped http.ts: comment only.",
)


def test_full_report_has_every_section():
    md = render_markdown(FULL, "https://github.com/o/r/actions/runs/1")
    assert md.startswith(MARKER + "\n## 🧪 Test agent: ✅ tests written and verified")
    assert "Decided 2 file(s); 1 test file(s) written, all green." in md
    assert "| backend | ✅ pass | ✅ pass | 42.42% → 48.10% (statements+branches) |" in md
    assert "| `backend/app/features/todos/router.py` | update | `backend/tests/features/todos/test_router.py` |" in md
    assert "| `frontend/src/lib/http.ts` | skip | — | comment-only change |" in md
    assert "### Dropped tests" in md and "AssertionError: 1 != 2" in md
    assert "### Suspected bugs" in md and "`test_blank`" in md
    assert "> Pinned the due-soon filter.\n> Skipped http.ts: comment only." in md
    assert "Turns: 7, tokens: 12,345 in (+90,000 cached), 678 out" in md
    assert "[Workflow run](https://github.com/o/r/actions/runs/1)" in md


def test_nothing_to_do_is_short_and_lists_ignored_files():
    md = render_markdown(make_report(status="nothing_to_do", stop_reason=None, usage=None,
                                     ignored=[{"path": "docs/x.md", "reason": "not application source"}]))
    assert "⚪ nothing to test" in md and "no model was called" in md
    assert "### Decisions" not in md and "Turns:" not in md
    assert "`docs/x.md`: not application source" in md


def test_partial_and_failing_suite_are_called_out():
    md = render_markdown(make_report(
        status="partial", stop_reason="limit:time", limit_hit="time", check_failed=True,
        suites={"frontend": {"before": suite(True, 47.68), "after": suite(False, None)}},
    ))
    assert "🟡 stopped early" in md and "the **time** limit was reached" in md
    assert "A full test suite fails with this PR's changes" in md
    assert "| frontend | ✅ pass | ❌ fail (exit 1) | 47.68% → n/a (lines) |" in md


def test_error_report_shows_the_error():
    md = render_markdown(make_report(status="error", stop_reason=None, check_failed=True, usage=None,
                                     error="ConnectionError: API unreachable"))
    assert "❌ agent error" in md and "The agent failed: ConnectionError: API unreachable" in md
    assert "A full test suite fails" not in md


@pytest.mark.parametrize("hostile, absent", [
    ("<img src=x onerror=alert(1)>", "<img"),
    ("ping @octocat now", "@octocat"),
    ("[click](https://evil.example)", "[click](https://evil.example)"),
    (f"{MARKER} spoof", MARKER + " spoof"),
    ("a | b", "a | b"),
])
def test_model_text_is_neutralized(hostile, absent):
    report = make_report(
        decisions=[{"path": "backend/app/x.py", "side": "backend", "action": "skip", "reason": hostile,
                    "test_file": "backend/tests/test_x.py"}],
        summary=hostile,
    )
    md = render_markdown(report)
    assert absent not in md
    assert md.count(MARKER) == 1


def test_test_output_cannot_break_out_of_its_fence():
    output = "```\n## injected heading\n```"
    md = render_markdown(make_report(dropped=[{"path": "backend/tests/test_a.py", "action": "create",
                                               "reason": "x", "last_output": output}]))
    assert "````text\n```\n## injected heading\n```\n````" in md


def test_inline_flattens_and_caps_length():
    assert inline("a\nb\tc") == "a b c"
    assert len(inline("x" * 1000)) == 300


def test_huge_reports_are_truncated_under_the_comment_limit():
    big = [{"path": f"backend/tests/test_{i}.py", "action": "create", "reason": "r", "last_output": "y" * 2000}
           for i in range(60)]
    md = render_markdown(make_report(dropped=big))
    assert len(md) <= MAX_COMMENT_CHARS
    assert md.rstrip().endswith("artifacts.")
