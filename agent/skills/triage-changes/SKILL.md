---
name: triage-changes
description: Deciding create, update or skip for each triage target. Load first on every run.
---

# Triage changes

For each target, in order:

1. Read its change with `git_diff`, then the full source with `read_file`.
2. When `test_exists` is true, read the test file and find which changed behaviour it already covers.
3. Decide, then `record_decision` with a one-sentence reason that names the specific behaviour.

## Decisions

- **create**: no test file exists and the target has testable behaviour (branching, validation, transformation, error handling, an endpoint, a query).
- **update**: a test file exists and the change adds or alters behaviour those tests leave **uncovered** (a new branch, parameter, return shape, endpoint or error path), or the change breaks an existing test.
- **skip**: the change is behaviour-neutral (formatting, comments, imports, renames, type hints), the existing tests already cover the changed behaviour, or the file is pure wiring or declaration with no logic of its own.

A good reason is specific: "new `due_soon` filter branch in `list_todos` has no test", not "file changed".

## Full mode

When the triage says full-repo mode, there is no diff: each target is an existing file with a coverage gap, listed with its `coverage` and `missing_lines`. Read the source and its tests, then decide:

- **create** or **update** to cover the uncovered lines that carry behaviour (branches, error paths, handlers).
- **skip** only when the uncovered lines are untestable wiring, with a reason that says so.

The reason names the behaviour the new tests cover, such as "error mapping for 422 and network failures in `request` has no test".

## Scope

An update adds test functions for the changed behaviour and repairs tests the change broke. Existing green tests stay as they are.
