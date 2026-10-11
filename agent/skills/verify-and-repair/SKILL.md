---
name: verify-and-repair
description: Running written tests and repairing failures, within each file's repair budget. Load before the first run_tests call.
---

# Verify and repair

Each test file gets a **repair budget** of 3: after its first failed run you may repair and rerun it three times. `run_tests` reports what is left. A file still red when its budget is spent is dropped from the output, so spend each repair on a real diagnosis.

## Loop, per file

1. Run the file with `run_tests`.
2. Green: the file is done.
3. Red: read the failure and **diagnose** before editing. Name the cause to yourself: a wrong import or fixture, a wrong assumption about the code, a flaky dependency on time or order, or code that really behaves wrongly.
4. Fix the cause:
   - **Test mistake**: re-read the source and fix the test so it asserts what the code does.
   - **Source bug**: the code contradicts its evident intent (its name, docstring, the rest of the change, or how callers use it). Remove that one test case, call `flag_suspected_bug` with what you expected and what the code does, and rerun so the rest of the file stays green.
5. Rewrite the whole file with `write_test_file` and go back to step 1.

## Rules

- Only fix the test you are working on. Tests that were already green before your change stay unchanged.
- A failing assertion is never fixed by asserting whatever the code returned without first checking it against the source. Tests that only mirror output protect nothing.
- When the budget is spent, stop editing that file and move on; the runtime drops it and reports its last failure.
