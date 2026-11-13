---
name: critique
description: Adversarially review a plan, specification or diff and report only findings that survive refutation. Use after a plan is written and before it is executed.
allowed-tools: Read, Glob, Grep, Bash, Write
argument-hint: the plan or spec to critique
depends-on: plan
---

# Critique

## Purpose

Find what is wrong before it is built. The value is not the number of findings; it
is that every finding written down survived an attempt to refute it and carries
evidence.

## Activation

- A plan or spec exists and has not been executed.
- The user asks for a review of an approach.

## Fixed rules

1. Be adversarial. Try to refute each finding before writing it down. A finding
   you could not refute is worth more than three you did not test.
2. Grade every finding CONFIRMED (verified against the codebase) or UNVERIFIED
   (state what you could not check and why).
3. Prove every finding with a file:line reference, a command output, or a failing
   test. Never assert a plausible but unchecked conclusion.
4. Cite plan line numbers only from the copy you read in this run.
5. Check the edge cases specific to the area: concurrency, nulls, error paths,
   boundaries. A generic "find bugs" pass is not enough.
6. Re-scan until two consecutive passes surface nothing new.
7. Require every chapter to state affected files and verification. Raise it as a
   finding when either is missing.
8. Do not edit the plan or the code. This phase writes the critique only.

## Procedure

1. Run the deterministic checks first: `zyrompts plan-critique <plan.md>`. These
   catch missing sections, missing verification, and paths that do not exist.
2. Read the plan against the actual codebase. Verify every path exists, every
   symbol is real, every command runs.
3. Evaluate: clarity, completeness, ordering, feasibility, risk, standards
   compliance, scope, testability, affected files.
4. Attempt to refute each candidate finding. Discard the ones that do not survive.
5. Write the critique in chapter order, with a summary table at the top.

## Output format

Write to `.zyrompts/plans/<slug>/critique.md`.

```
# <Plan title>
Iteration: <n>

## Summary
- <assessment>
- CONFIRMED: <n>, UNVERIFIED: <n>

## <Chapter title>
Confidence: CONFIRMED | UNVERIFIED
Description: <issue>
Evidence: <file:line, command output, or failing test>
Suggested solution: <fix>
```

## Failure handling

- Nothing found after two passes: say "No new findings" and stop. Do not pad.
- The plan is too vague to critique: report that as the finding.
- A finding depends on a fact you cannot check: grade it UNVERIFIED and say what
  would confirm it.

## Evaluation cases

- Chapter with no verification section -> CONFIRMED medium finding.
- Plan references `src/foo.py` that does not exist -> CONFIRMED high finding.
- Suspected race condition -> UNVERIFIED unless a test reproduces it.

## Version

1.0.0. Depends on: plan. Platforms: all.
