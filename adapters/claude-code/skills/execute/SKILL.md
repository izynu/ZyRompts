---
name: execute
description: Implement an approved plan step by step with tests and evidence. Use after a plan is approved, or when the user asks to implement a plan.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion
argument-hint: plan name
---

# Execute

## Purpose

Turn an approved plan into working code, one verified step at a time, with state
saved after every step so a crash costs one step, not the run.

## Fixed rules

1. Never report a step as done, fixed or working until a check backs it. A step
   whose tests did not run is reported as unverified, never as complete.
2. Where a test suite exists, write the test first, confirm it fails, then
   implement until it passes. Never edit a passing test to fit new code.
3. Prove claims with evidence: command output, a test run, or a file:line.
4. Output complete file contents; never truncate with "... rest of code ...".
5. Commit only when asked. Never append a co-author trailer unless the project
   explicitly requires it.
6. Be brief. No filler, no emoji, no em dashes.

## Procedure

1. Load `.zyrompts/state/project.json` if it exists. If a previous execution was
   interrupted, offer resume or restart and wait for the answer.
2. Read `plan.md`, `critique.md` if present, and the project standards file.
3. Detect the test command. Record it. If no suite exists, say so and state that
   verification will be by build, type check and diff only.
4. Parse the plan into steps in dependency order. Present the step list with the
   files each step is likely to touch, and wait for confirmation.
5. For each step:
   - Save state before starting, including the step index.
   - Ask before any high-risk operation: migrations, deletions, config changes,
     external side effects, anything irreversible.
   - Write the test first where a suite exists; show it failing.
   - Implement the step.
   - Run the verification the plan names. Show the output verbatim.
   - Update state and append to the execution log.
6. On error: save state, read the actual error, present recovery options (fix and
   retry, skip, rollback, stop) and wait.
7. On completion: run the full suite one last time, then hand off to `verify`.

## Output format

Write `.zyrompts/plans/<slug>/execution-log.md`:

```
## Step N - <name>
Started: <iso> | Duration: <s>
Files: <added/modified/deleted>
Verification: `<command>` -> <result>
Status: COMPLETED | SKIPPED | FAILED | UNVERIFIED
```

## Failure handling

- A test passes before the implementation exists: the test is wrong. Fix the test.
- The environment is broken: stop and report, do not work around it silently.
- A step turns out to need a design decision: stop and ask, do not improvise.

## Evaluation cases

- Plan with three chapters and a pytest suite -> three failing tests, three
  passing runs, one final full-suite run.
- Plan with no suite -> steps verified by build and diff, results labelled
  unverified by tests.

## Version

1.0.0. Depends on: plan, critique. Platforms: all.
