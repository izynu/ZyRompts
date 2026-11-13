---
name: zy-debugging
description: Find and fix a defect from its root cause, with a reproduction that proves it. Use when something fails, crashes, or behaves differently than expected.
license: MIT
---

# Debugging

## Purpose

Replace the symptom with the cause. A fix that makes the error disappear without
explaining it is a new bug with a delay.

## Procedure

1. Reproduce it. Get the exact command, input, or sequence that fails. If you
   cannot reproduce it, say so and gather more evidence rather than guessing.
2. Read the actual error. Not the summary of it. The stack trace, the failing
   assertion, the exit code.
3. Locate the failure point. Use `Grep` for the error text, `Read` the file, and
   trace the data backward from the failure to where it first goes wrong.
4. Form one hypothesis. State it. Design the cheapest check that would disprove
   it. Run the check.
5. If the hypothesis survives, fix the cause, not the symptom. If it does not,
   discard it and form the next one. Do not stack fixes.
6. Add a regression test that fails without the fix and passes with it.
7. Report: cause, evidence, fix, and the test that proves it.

## Anti-patterns

- Adding a try/except around the failure to hide it.
- Changing several things at once so you cannot tell which worked.
- "It works now" with no explanation of why it failed before.
- Fixing the test instead of the code.

## Failure handling

- Cannot reproduce: report the missing information needed, do not ship a guess.
- The cause is environmental: say so, and give the check that confirms it.
- The fix requires a design change: stop and plan it, do not smuggle it into a
  bug fix.

## Evaluation cases

- `TypeError: NoneType has no attribute 'x'` -> trace where None enters, fix there.
- Flaky test -> identify the shared state or timing assumption, prove it.

## Version

1.0.0. Depends on: none. Platforms: all.
