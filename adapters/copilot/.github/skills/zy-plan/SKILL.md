---
name: zy-plan
description: Write an implementation plan with ordered chapters, affected files and verification steps. Use before implementing any non-trivial change, or when the user asks for a plan or approach. Use when the user runs /zy-plan.
license: MIT
---

# Plan

## Purpose

Turn a specification into ordered work where every chapter names the files it
touches and the check that proves it is done. A plan that cannot be critiqued
chapter by chapter is not a plan.

## Activation

- A non-trivial change is about to be implemented.
- The user asks for a plan, an approach, or a breakdown.
- The intake hook routed the request to the planned or full workflow.

## Procedure

1. Read the spec, `CLAUDE.md`/`AGENTS.md`, and the files the change touches. Do not
   plan code you have not looked at.
2. List every file the plan will create, modify, or delete. Verify each existing
   path with `Glob` before writing it down. Mark new files as new.
3. Order chapters by dependency: independent work first, smallest to largest
   within a level, dependent work after what it depends on.
4. For each chapter write: the change, the affected files, and the verification.
   Verification names the test to write or the command to run and the output that
   means success.
5. Where the project has no test infrastructure, say so in the chapter instead of
   inventing a harness.
6. Flag any chapter that exceeds roughly one focused session; recommend a split.
7. Re-read the plan once for contradictions between chapters before presenting.

## Output format

Write to `.zyrompts/plans/<slug>/plan.md`.

```
# <Title>

## Summary
<one paragraph: what changes and why>

## Chapter 1 - <name>
<what changes>

Affected files:
- `path/to/file.py` (modify)

Verification:
- `pytest tests/test_x.py::test_y` passes

## Risks
- ...
```

## Failure handling

- A path cannot be verified: mark it "to be determined" and raise it as an open
  item rather than guessing.
- The plan exceeds 10 chapters: split it and say so.
- Requirements are still unclear: stop and use `clarify` first.

## Evaluation cases

- "add a health endpoint" -> one chapter, one file, one curl check.
- "migrate auth to OAuth" -> multiple chapters with ordering and rollback notes.

## Version

1.0.0. Depends on: specify. Platforms: all.
