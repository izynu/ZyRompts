---
name: tdd
description: Drive a change test-first. Use when the project has a test suite and the change has observable behavior, or when the user asks for TDD.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
argument-hint: the behavior to implement
---

# TDD

## Purpose

Make correctness visible before it is claimed. The cycle is red, green, refactor,
and the discipline is that a test must fail for the right reason before it is
allowed to pass.

## Activation

- The project has a test suite and the change has observable behavior.
- The user asks for tests first.

Do not activate when there is no test infrastructure. Inventing a harness the
project does not use creates maintenance debt, not safety.

## Procedure

1. Find the test command and the nearest existing test file. Match its style.
2. Write the smallest test that expresses the required behavior.
3. Run it. Confirm it fails, and confirm it fails for the expected reason. A test
   that fails because of a typo in the test is not red, it is broken.
4. Write the minimum implementation that makes it pass.
5. Run the test. It must pass.
6. Refactor with the test as the safety net. Re-run after every change.
7. Repeat for the next behavior. One behavior per cycle.

## Rules

- Never edit a passing test to accommodate new code.
- Never add a test that asserts what the code already does just to raise coverage.
- Never mock so much that the test only proves the mock works.
- A flaky test is a defect in the test; fix it before building on it.

## Failure handling

- No test runner: stop and use the `execute` skill's build-and-diff verification.
- The test cannot be written without a design decision: stop and ask.
- The suite is already red: fix or quarantine the pre-existing failure first, and
  say which failure was already there.

## Evaluation cases

- "add input validation" -> test for the invalid input, red, then the validator.
- "fix the null deref" -> reproducing test, red, then the guard.

## Version

1.0.0. Depends on: execute. Platforms: all.
