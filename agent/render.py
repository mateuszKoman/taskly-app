"""Render report.json as Markdown for the PR comment and the job summary.

Model-written strings (reasons, summary, test names, test output) are untrusted: they are escaped so they
cannot inject HTML, ping people, add links, break tables or fences, or spoof the comment marker.
"""

from __future__ import annotations

import re

MARKER = "<!-- taskly-test-agent -->"
MAX_COMMENT_CHARS = 60_000  # GitHub's limit is 65,536
MAX_INLINE_CHARS = 300

STATUS = {
    "ok": ("✅", "tests written and verified"),
    "nothing_to_do": ("⚪", "nothing to test"),
    "partial": ("🟡", "stopped early"),
    "incomplete": ("🟡", "incomplete"),
    "error": ("❌", "agent error"),
}
ACTION_LABEL = {"create": "create", "update": "update", "skip": "skip", None: "—"}


def neutralize(text: str) -> str:
    text = text.replace(MARKER, "")
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"@(?=\w)", "@​", text)  # no mentions


def inline(text: str | None, limit: int = MAX_INLINE_CHARS) -> str:
    text = " ".join(str(text or "").split())
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    text = neutralize(text)
    return re.sub(r"([\\`*_\[\]()|!#])", r"\\\1", text)


def code(text: str) -> str:
    """Inline code span for paths; backticks inside are dropped."""
    return f"`{neutralize(str(text)).replace('`', '')}`"


def fenced(text: str) -> str:
    text = text.replace(MARKER, "")
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{text.rstrip()}\n{fence}"


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}%"


def suite_cell(result: dict | None) -> str:
    if not result:
        return "—"
    return "✅ pass" if result["passed"] else f"❌ fail (exit {result['exit_code']})"


def headline(report: dict) -> str:
    status = report["status"]
    decisions = report["decisions"]
    written = report["files_written"]
    if status == "nothing_to_do":
        return "No testable source changes in this PR, so no tests were needed and no model was called."
    if status == "ok":
        return f"Decided {len(decisions)} file(s); {len(written)} test file(s) written, all green."
    if status == "partial":
        return f"Stopped early: the **{report['limit_hit']}** limit was reached. Green tests were kept; the rest was dropped."
    if status == "incomplete":
        return f"The agent stopped before finishing ({inline(report['stop_reason'])}). Green tests were kept; the rest was dropped."
    return f"The agent failed: {inline(report.get('error'))}"


def suites_section(report: dict) -> list[str]:
    if not report["suites"]:
        return []
    lines = ["", "| Side | Full suite before | Full suite after | Coverage before → after |", "|---|---|---|---|"]
    for side, phases in report["suites"].items():
        before, after = phases.get("before"), phases.get("after")
        metric = (after or before or {}).get("metric", "")
        coverage = f"{pct((before or {}).get('coverage'))} → {pct((after or {}).get('coverage'))} ({metric})"
        lines.append(f"| {side} | {suite_cell(before)} | {suite_cell(after)} | {coverage} |")
    return lines


def decisions_section(report: dict) -> list[str]:
    if not report["decisions"]:
        return []
    lines = ["", "### Decisions", "", "| File | Decision | Test file | Reason |", "|---|---|---|---|"]
    for d in report["decisions"]:
        lines.append(
            f"| {code(d['path'])} | {ACTION_LABEL.get(d['action'], '—')} | "
            f"{code(d['test_file']) if d['action'] in ('create', 'update') else '—'} | {inline(d['reason'])} |"
        )
    return lines


def files_section(report: dict) -> list[str]:
    if not report["files_written"]:
        return []
    lines = ["", "### Test files", ""]
    for f in report["files_written"]:
        lines.append(f"- {code(f['path'])}: {'created' if f['action'] == 'create' else 'updated'}, ✅ green")
    return lines


def dropped_section(report: dict) -> list[str]:
    if not report["dropped"]:
        return []
    lines = ["", "### Dropped tests", "", "These were not green when the run ended, so they are not part of the change."]
    for d in report["dropped"]:
        lines += ["", f"<details><summary>{code(d['path'])}: {inline(d['reason'])}</summary>", ""]
        lines += [fenced(d["last_output"] or "(no output)"), "", "</details>"]
    return lines


def bugs_section(report: dict) -> list[str]:
    if not report["suspected_bugs"]:
        return []
    lines = ["", "### Suspected bugs", "", "The agent removed these test cases because the code itself looks wrong:", ""]
    for b in report["suspected_bugs"]:
        lines.append(f"- {code(b['test_file'])} {code(b['test_name'][:120])}: {inline(b['reason'])}")
    return lines


def summary_section(report: dict) -> list[str]:
    summary = report.get("summary", "").strip()
    if not summary:
        return []
    quoted = [f"> {inline(line, 1_000)}" if line.strip() else ">" for line in summary.splitlines()[:30]]
    return ["", "### Agent summary", "", *quoted]


def details_section(report: dict, run_url: str | None) -> list[str]:
    usage = report.get("usage") or {}
    rows = [f"- Model: {code(report['model'])}"]
    if usage:
        rows.append(
            f"- Turns: {usage['turns']}, tokens: {usage['input_tokens']:,} in "
            f"(+{usage['cache_read_input_tokens']:,} cached), {usage['output_tokens']:,} out"
        )
    if report["skills_loaded"]:
        rows.append(f"- Skills loaded: {', '.join(code(s) for s in report['skills_loaded'])}")
    rows.append(f"- Base: {code(report['base'])} @ {code(report['merge_base'][:12])}")
    if report["ignored"]:
        rows.append(f"- Ignored files ({len(report['ignored'])}):")
        rows += [f"  - {code(i['path'])}: {inline(i['reason'])}" for i in report["ignored"][:50]]
        if len(report["ignored"]) > 50:
            rows.append(f"  - … and {len(report['ignored']) - 50} more")
    if run_url:
        rows.append(f"- [Workflow run]({run_url})")
    return ["", "<details><summary>Run details</summary>", "", *rows, "", "</details>"]


def render_markdown(report: dict, run_url: str | None = None) -> str:
    icon, label = STATUS.get(report["status"], ("❔", report["status"]))
    lines = [MARKER, f"## 🧪 Test agent: {icon} {label}", "", headline(report)]
    if report.get("check_failed") and report["status"] != "error":
        lines += ["", "❌ **A full test suite fails with this PR's changes.** See the table below."]
    for section in (suites_section, decisions_section, files_section, dropped_section, bugs_section, summary_section):
        lines += section(report)
    lines += details_section(report, run_url)
    text = "\n".join(lines) + "\n"
    if len(text) > MAX_COMMENT_CHARS:
        cut = "\n\n… truncated; the full report is in the workflow run's artifacts.\n"
        text = text[: MAX_COMMENT_CHARS - len(cut)] + cut
    return text
