---
name: verify
description: Prove a change works before claiming it does. Use before reporting completion, merging, or handing work back.
allowed-tools: Read, Glob, Grep, Bash
argument-hint: what to verify
depends-on: execute, code-review
---

# Verify

## Purpose

Convert "it should work" into "here is the output that shows it works". The
deliverable of this skill is evidence, not confidence.

## Activation

- Before any statement that a task is done, fixed, or working.
- Before merge or handoff.
- When the `Stop` hook has flagged a completion claim with no evidence.

## Procedure

1. Restate the acceptance criteria. If the plan had none, derive them from the
   request and say that you derived them.
2. Run each check, in this order, and capture the raw output:
   - Build or type check.
   - Full test suite, not a subset.
   - The specific scenario from the request, executed end to end.
   - The regression test for any bug that was fixed.
3. Compare the result to each criterion. Mark it PASS, FAIL, or UNVERIFIED.
   UNVERIFIED is for a criterion you could not check, and it is never rounded up
   to PASS.
4. Check the diff for what should not be there: debug prints, commented-out
   code, secrets, TODO markers, unrelated edits.
5. Report the table. Any FAIL blocks completion. Any UNVERIFIED must be named
   explicitly to the user, with the reason.

## Rules

- Never report a check you did not run. A command you intended to run is not a
  result.
- Never quote a summary of the output in place of the output when the user asked
  for proof.
- A test that was skipped is reported as skipped, not as passing.
- If the suite was already red before the change, say which failures pre-existed,
  so the change is not blamed for them and not excused by them.

## Output format

```
| Criterion | Check | Result | Evidence |
|---|---|---|---|
| <criterion> | `<command>` | PASS/FAIL/UNVERIFIED | <exit code, counts, output line> |

Verdict: COMPLETE | INCOMPLETE (<n> failing, <n> unverified)
```

## Failure handling

- The environment cannot run the suite: report INCOMPLETE with the blocker, and
  offer the narrower check that is possible.
- A criterion is ambiguous: state the reading you used, and flag it for
  confirmation.
- A check passes for the wrong reason: investigate before reporting PASS.

## Evaluation cases

- Three criteria, full suite green, scenario run -> COMPLETE with a full table.
- Suite green but the scenario was never executed -> that row is UNVERIFIED, and
  the verdict is INCOMPLETE.
- Pre-existing failure in an unrelated module -> reported as pre-existing, with
  its name.

## Version

1.0.0. Depends on: execute, code-review. Platforms: all.
