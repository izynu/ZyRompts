---
name: zy-specify
description: Turn an agreed request into a specification with testable acceptance criteria. Use before planning any non-trivial feature, or when a request has no written definition of done.
allowed-tools: Read, Write, Glob, Grep
---

# Specify

## Purpose

Produce the document a plan can be built from: what is being built, why, what is
explicitly out of scope, and how completion is proven. Without this, a plan
encodes guesses and the critique has nothing to check against.

## Activation

- A request is non-trivial and no acceptance criteria exist.
- A plan is about to be written.
- The user asks for a spec, a PRD, or a definition of done.

## Procedure

1. State the problem, not the solution: who is affected, what is wrong today, why
   it matters now. One paragraph.
2. State the goal in one sentence that a stranger could verify.
3. Write requirements as numbered, testable statements. Each must be checkable
   with a command, a test, or a visible behavior. Reject "should be fast" and
   replace it with a measurable bound.
4. Write acceptance criteria as a checklist. Each criterion names the evidence
   that will prove it: a test name, a command, or an observable result.
5. Write out-of-scope explicitly. Name the tempting adjacent work you are not
   doing, so scope creep has something to collide with.
6. Write constraints: compatibility, performance bounds, dependencies allowed or
   forbidden, platforms, deadline.
7. Write open questions. Anything unresolved is listed, not guessed.
8. Verify the spec: every requirement has an acceptance criterion, every
   criterion has evidence, out-of-scope is non-empty.

## Output format

Write to `.zyrompts/specs/<slug>.md` unless the project has its own docs layout.

```
# <Title>

## Problem
## Goal
## Requirements
1. ...
## Acceptance criteria
- [ ] <criterion> - evidence: <test/command/observation>
## Out of scope
## Constraints
## Open questions
```

## Failure handling

- Requirements cannot be made testable yet: mark them open and say what decision
  would make them testable. Do not invent a threshold.
- The user wants to skip the spec: say what will be lost (no verifiable
  completion) and proceed only if they accept it.

## Evaluation cases

- "add rate limiting" -> requirements naming the limit, the window, the response
  code; criteria naming the test that sends N+1 requests.
- "make the app faster" -> rejected as untestable until a metric and a bound are
  chosen.

## Version

1.0.0. Depends on: clarify. Platforms: all.
