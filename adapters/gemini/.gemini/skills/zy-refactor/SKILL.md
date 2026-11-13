---
name: zy-refactor
description: Restructure code without changing behavior, with tests as the safety net. Use when code needs cleanup, extraction, or restructuring and behavior must stay identical.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

# Refactor

## Purpose

Improve structure while provably preserving behavior. The proof is the test
suite, so a refactor without tests is a rewrite in disguise and must be labelled
as one.

## Procedure

1. Confirm the behavior contract. Which tests cover this code? If none, write
   characterization tests that capture current behavior before touching it.
2. Establish the baseline: run the suite, record the result.
3. Make one structural change at a time: extract, inline, rename, move, or
   introduce a seam. Never mix a refactor with a behavior change in one step.
4. Run the suite after every step. A red suite means revert, not continue.
5. Stop when the structure is good enough. Refactoring has no natural end; the
   goal is the specific smell you set out to remove.

## Rules

- One concern per commit or step.
- No behavior change inside a refactor. If behavior must change, split it out.
- Keep the public interface stable unless the task is explicitly an API change.
- Do not refactor code you were not asked to touch; it hides the real diff.

## Failure handling

- No tests and characterization is impractical: say so, and require explicit
  approval before proceeding without a safety net.
- The refactor reveals a bug: report it separately, do not fix it inline.
- The suite was already failing: record which failures pre-existed.

## Evaluation cases

- Extract a 200-line function into named helpers, suite stays green at each step.
- Rename a module across the codebase, imports updated, suite green.

## Version

1.0.0. Depends on: tdd (optional). Platforms: all.
