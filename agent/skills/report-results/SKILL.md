---
name: report-results
description: Writing the final run summary shown to PR reviewers. Load once every target is decided and every test file is green or out of budget.
---

# Report results

The runtime builds the PR report from recorded facts: decisions, files, test runs, coverage, dropped tests, suspected bugs. Your final message becomes its **Agent summary** section, the one part a reviewer reads as prose. Make it add what the facts cannot: *why*.

## Before writing

- Every target has a decision recorded with `record_decision`, and each reason names a specific behaviour.
- Every suspected bug is flagged with `flag_suspected_bug`; the summary refers to it, never instead of it.

## The summary

Plain sentences, at most 6 lines, no headings, tables, links or code blocks:

1. What behaviour the new or updated tests pin down, in reviewer terms ("the `due_soon` filter excludes completed todos").
2. What you skipped and the deciding reason, when it is not obvious from the decision table.
3. Anything a reviewer should look at: suspected bugs, a file you could not get green, an assumption you made about intended behaviour.

Write for a reviewer who has the decision table open beside it: leave out file lists, counts and pass/fail tallies, which the report already shows.
