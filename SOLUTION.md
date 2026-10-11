# Solution: a test agent for Taskly pull requests

A custom Python agent, with reusable skills, that runs on every pull request. It decides which changed source files need new or updated unit tests, writes them, proves they pass, and reports the result on the PR. Run locally in full-repo mode, the same agent wrote the missing baseline tests for the backend and frontend.

```
PR opened / updated
 └─ gate      (read-only)      skip forks, the skip-test-agent label, and the agent's own commits
 └─ generate  (read-only + API key in one step)
      triage (no model) → agent loop (model + skills + sandboxed tools) → drop red tests
      → full suites with coverage before/after → report.json, summary.md, tests.patch
 └─ publish   (write, no API key, no PR code executed)
      validate patch with base-branch code → commit to the PR branch → one PR comment, updated in place
```

## Main technical decisions

| Decision | Why |
|---|---|
| **Own agent loop on the Anthropic SDK** (`agent/runtime.py`) rather than a ready-made coding agent | The runtime, not the model, owns the limits (turns, tokens, time, repair budget) and the definition of done. Tools are exactly the ones the task needs, so the security story is small and testable. |
| **Deterministic code around the model** | Triage, test execution, dropping red tests, coverage, the report and the PR comment are plain code. The model only decides per file and writes tests. Facts in the report come from recorded tool calls, never from model prose. |
| **Skills as Markdown, loaded on demand** (`agent/skills/*/SKILL.md`) | Only skill descriptions sit in the system prompt; the agent loads a full skill when it reaches that step. Each skill holds one concern (triage, backend tests, frontend tests, repair, report) and is reusable across PR and full-repo runs. |
| **Least-privilege tools** | The model can read the repo (secrets files refused), write *only* test files (`backend/tests/**/test_*.py`, `frontend/src/**/*.test.ts(x)`), and run fixed test commands. No shell tool. Paths are normalised; `..`, absolute paths and symlinks are refused. Test subprocesses get an environment with secrets removed. |
| **Verification is part of "done"** | Every written test file must be green (pytest, or Vitest plus `tsc` for type errors). Each file gets 3 repairs; anything still red is removed and reported. Full suites run before and after with coverage. |
| **Split `generate` / `publish` jobs** | The job that runs PR code has no write token; the job with write access has no API key and runs no PR code. Its patch validator and comment renderer come from the base branch, so a PR cannot loosen the rules it is checked by. |
| **Config as the single source of truth** | Triage reads the coverage include/exclude lists from `backend/pyproject.toml` and `frontend/vite.config.ts`. The agent's write allowlist and the publish validator share one set of path rules (`agent/policy.py`). |
| **Model: `claude-sonnet-5-5` at medium effort** | Fast and cheap enough to run on every PR, strong enough for test writing. Changeable with the `AGENT_MODEL` repository variable. |

## Running the PR workflow

**Prerequisites**
- Repository secret `ANTHROPIC_API_KEY`.
- Settings → Actions → General → Workflow permissions: **Read and write** (the `publish` job pushes the tests).
- PRs from branches of this repository. Fork PRs are skipped, because they cannot use the secret.
- Optional: repository variable `AGENT_MODEL`; label `skip-test-agent` to skip one PR.

**Usage:** open or push to a PR. `.github/workflows/test-agent.yml` runs automatically. Results appear as a commit from `github-actions[bot]` with the tests (trailer `Test-Agent: generated`), one PR comment that is updated on every push, the job summary, and the `test-agent-output` artifact (`triage.json`, `report.json`, `summary.md`, `tests.patch`). The check is red only when a full suite fails with the agent's tests applied, or the agent itself fails.

PRs that change `agent/**` also run the agent's own unit tests (`.github/workflows/agent-tests.yml`, no secrets).

**Locally** (Python 3.14, frontend dependencies installed):
```sh
python3.14 -m venv .venv && .venv/bin/pip install -r agent/requirements.txt
.venv/bin/python -m pytest agent/tests -q                       # agent unit tests, no API key
.venv/bin/python -m agent triage --base main                    # what would be targeted, no model call
ANTHROPIC_API_KEY=... .venv/bin/python -m agent pr --base main  # the PR flow on local changes
ANTHROPIC_API_KEY=... .venv/bin/python -m agent full            # close coverage gaps across the repo
```

## Where the agent and skills live, and how a run uses them

| Path | Role |
|---|---|
| `agent/AGENT.md` | The agent: role, run steps, rules, definition of done. Becomes the system prompt with the skill index. |
| `agent/skills/triage-changes` | Decide `create` / `update` / `skip` per file, with a specific reason (PR and full mode). |
| `agent/skills/write-backend-tests` | pytest conventions of this repo: fixtures, repository mocks, router tests through `TestClient`. |
| `agent/skills/write-frontend-tests` | Vitest + Testing Library conventions: fixtures, design-system mocks, `userEvent`, react-query, fake timers. |
| `agent/skills/verify-and-repair` | The run → diagnose → fix loop within the repair budget; when to flag a suspected source bug. |
| `agent/skills/report-results` | The reviewer-facing summary. |
| `agent/runtime.py`, `tools.py`, `policy.py` | Agent loop and limits; tools; path policy. |
| `agent/triage.py`, `full.py` | Targets from a PR diff, or from coverage gaps. |
| `agent/verify.py`, `pipeline.py` | Full suites with coverage, dropping red tests; the run sequence. |
| `agent/render.py`, `patch.py` | PR comment (model text escaped); patch validation for `publish`. |
| `.github/workflows/test-agent.yml` | `gate` → `generate` → `publish`. |

**A run, step by step:** triage lists the target files (no model call; nothing testable ends the run here). Both full suites run for the baseline. The agent loads `triage-changes` and records a decision per target. For each `create` or `update` it loads the writing skill for that side and writes the test file. It loads `verify-and-repair` and runs each file until it is green or out of repairs. It loads `report-results` and writes its summary. The runtime refuses to finish while a target has no decision or a written file is red with repairs left. Then it drops red files, reruns the suites, and writes the report. `publish` validates and commits the patch and updates the PR comment.

## Example run: PR #9, "due soon"

[PR #9](https://github.com/mateuszKoman/taskly-app/pull/9) adds a "due soon" feature (backend: computed `due_soon` field and `?due_soon=true` filter; frontend: badge and filter) with no tests, and was pushed twice.

**Round 1: new feature** ([run](https://github.com/mateuszKoman/taskly-app/actions/runs/38136277783), about 2.5 minutes)

| File | Decision | Reason given by the agent |
|---|---|---|
| `backend/.../due.py` | create `test_due.py` | New due_soon_range/is_due_soon logic has no tests. |
| `backend/.../repository.py` | update | New due_soon where-clause branch in list is untested. |
| `backend/.../router.py` | update | New due_soon query param routing to repo.list(due_soon=True) is untested. |
| `frontend/.../TodoFilters.tsx` | update | New 'Due soon' status option is untested. |
| `frontend/.../TodoItem.tsx` | update | New Due soon badge when todo.due_soon is untested. |
| `frontend/.../utils/todos.ts` | update | New 'due-soon' filter branch in selectTodos is untested. |

- Skills loaded: all five. 7 turns, 9,765 output tokens (+63,792 cached input).
- 6 of 6 test files green on the first run; nothing dropped; no suspected bugs. Files the coverage config excludes (`schemas.py`, `types.ts`, the test fixture) were skipped by triage with that reason.
- Suites green before and after. Coverage: backend 94.02% → 97.83%, frontend 90.44% → 91.08%.
- Committed by `github-actions[bot]` as `0277195` (106 lines in 6 files), plus one PR comment.

**Round 2: changed code** ([run](https://github.com/mateuszKoman/taskly-app/actions/runs/38137138733), about 3 minutes)

The second push moved the "due soon" filter from the client to the API (`?due_soon=true`, a separate query cache key, cache invalidation in the create/update/delete mutations), and changed `useTodoFilters` so that two existing tests broke.

- **13 targets, 6 skipped** with reasons such as "Existing tests cover utc_now, due_soon_range and is_due_soon branches", because round 1's tests already covered them. All three backend files were skipped, so the backend skill was not even loaded.
- **Repaired broken tests**: `useTodoFilters.test.ts` ("Hook no longer takes todos or returns `visible`, breaking existing tests") and the `TodosPage` mocks.
- **Covered the new code**: created `useTodosQuery.test.ts`, and updated the API, page and three mutation tests (7 files, +149 / −31 lines, all green on the first run).
- Frontend suite **red before, green after** (coverage 92.54% after; no "before" number because a failing Vitest run writes no coverage report). Backend unchanged at 97.83%.
- 11 turns, 14,889 output tokens. Committed as `ac2ece4`; the same PR comment was updated.
- The agent's summary flagged one of its own new page tests as weak ("it only confirms that nothing is shown").
- The run GitHub started for the agent's own commit was stopped by the gate: "Skipped because the latest commit was made by the test agent itself."

After both rounds the branch has backend 56 and frontend 72 passing tests, with `tsc` and Prettier clean.

## Baseline coverage (full mode)

Two local `python -m agent full` runs (8 targets each, largest coverage gaps first) wrote the missing tests. Every file was reviewed before committing.

| Suite | Start | After run 1 | After run 2 | Tests |
|---|---|---|---|---|
| Backend (statements + branches) | 42.42% | 93.94% | 97.58% | 21 → 45 |
| Frontend (lines) | 47.68% | 70.19% | 90.72% | 18 → 61 |

Review of run 1 found a type error (a fixture missing a required field) and formatting drift, which Vitest does not catch. Both were fixed, and the agent now type-checks frontend tests with `tsc` and formats them with Prettier.

## Assumptions

- Unit tests only: backend tests mock the database session, frontend tests run in jsdom. No end-to-end or database tests.
- PR authors are collaborators. Fork PRs are skipped rather than run with reduced rights.
- Tests are written against the code's current behaviour. When that behaviour looks wrong, the agent removes the test case and reports a suspected bug instead of changing source code.
- The PR head commit is tested (not GitHub's merge commit), so the patch applies cleanly to the PR branch.
- "Due soon" uses the server's UTC date.

## Limitations

- **The API key and the PR's code share a job.** Test subprocesses get a scrubbed environment, but a malicious test running as the same user could still read the agent process's environment. Today that is mitigated by skipping fork PRs.
- Changed files are tested in isolation by their paired test file. Cross-file effects are only caught by the full suite.
- Coverage before/after is measured on the whole suite, not on the changed lines.
- One run per PR head; a push while the agent runs cancels it, and a push that races `publish` is rejected and left to the next run.
- Model output varies between runs. Verification guarantees green tests, not identical tests.
- The agent's summary can use Markdown that the comment renderer escapes, so emphasis shows as literal characters.
- When a suite fails before the agent runs, no "before" coverage is available for that side.

## For production

- Run tests in a separate, network-restricted container or job that never sees the API key; pass only the patch between them.
- Open the tests as a suggested-changes review or a separate PR, instead of pushing to the author's branch.
- Measure and gate on coverage of changed lines (diff coverage), and add mutation testing to catch tests that only mirror output.
- Track cost, turns, drop rate and suspected-bug accuracy per run; keep an eval set of past PRs to tune prompts and skills safely.
- Cache dependency installs and run backend and frontend in parallel to cut run time.
- Support more test types (API contract tests against a real database) as separate, opt-in skills.
