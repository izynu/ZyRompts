---
name: code-review
description: Review a diff or change for correctness defects, independently of the author. Use after implementation, before merge, or when asked to review code.
allowed-tools: Read, Glob, Grep, Bash
argument-hint: diff, branch, or path to review
depends-on: execute
---

# Code Review

## Purpose

Find defects the author could not see. A review that only restates the diff is
worth nothing; a review that finds one real bug is worth the whole pass.

## Activation

- After `execute` finishes a chapter, before merge.
- The user asks for a review of a diff, branch, PR or path.
- Any change touching auth, input parsing, data writes or money.

## Inputs

- The change under review: `git diff`, a branch, or explicit paths.
- The requirements it claims to satisfy.
- The project's test command.

## Procedure

1. Read the change before the surrounding code, then read enough context to
   judge it: callers, tests, and the data it touches.
2. Establish the baseline: run the test suite. Record what was already failing.
3. Review in this order, because it is the order of cost:
   - Correctness: does it do what it claims for every input, including empty,
     null, huge, duplicate and concurrent?
   - Error handling: does a failure surface, or get swallowed?
   - Boundaries: off-by-one, inclusive versus exclusive, timezone, encoding.
   - Tests: does a test actually fail if the change is reverted?
   - Clarity: naming, dead code, duplicated logic, comment rot.
4. For each finding, grade it:
   - `CRITICAL`: data loss, security hole, or guaranteed production break.
   - `HIGH`: wrong result on a realistic input.
   - `MEDIUM`: wrong result on an edge input, or a maintenance trap.
   - `LOW`: clarity, style, naming.
   - `INFO`: observation, no action required.
5. Mark each finding `CONFIRMED` (you reproduced it, or traced the code path) or
   `UNVERIFIED` (you suspect it but have not proven it). Never present a
   suspicion as a confirmed defect.
6. Attach evidence: `file:line`, the input that triggers it, and the command or
   test that shows it.
7. Try to refute your own findings before reporting. A finding that survives an
   attempt to disprove it is worth reporting; one that does not is noise.
8. Report `BLOCK` if any CRITICAL survives, `REVISE` if any HIGH survives,
   otherwise `PASS`.

## Rules

- Never approve your own output. If you wrote the change, a separate reviewer
  or a fresh pass over the diff is required.
- Report defects, not preferences. Style opinions go in a separate, optional
  section.
- Do not rewrite the change while reviewing it. Review and fix are separate
  passes, or the diff you are judging disappears.
- Absence of findings is a legitimate result. Say what you checked, so the
  reader can judge the coverage.

## Output format

```
VERDICT: BLOCK | REVISE | PASS
Baseline: <test command> -> <n> passed, <n> failed (<pre-existing?>)

## <SEVERITY> - <one-line claim> [CONFIRMED|UNVERIFIED]
file:line
Trigger: <input or state>
Why it is wrong: <one or two sentences>
Evidence: <command output or trace>
Fix: <the smallest correct change>
```

## Failure handling

- Cannot run the tests: say so, and label every behavioural finding `UNVERIFIED`.
- The change is too large to review honestly: say so, and review it in slices.
- The finding needs a design decision: report it as a question, do not assume.

## Evaluation cases

- A diff that removes a null check: flagged HIGH CONFIRMED with the failing input.
- A diff with an unused import: LOW, no verdict impact.
- A diff whose new test passes when the fix is reverted: flagged HIGH, test is fake.

## Version

1.0.0. Depends on: execute. Platforms: all.
