# Critique: <artifact>

Subject: <plan or specification being reviewed>
Reviewer: <agent, never the author>
Verdict: BLOCK | REVISE | PASS
Findings: <n> surviving, <n> refuted (<n> CONFIRMED, <n> UNVERIFIED)

## Method

- Read for intent, then for defects.
- Every candidate finding was refuted once before it was reported.
- Checked against: <the code, tests, or docs used as evidence>

## CRITICAL

### <one-line claim> [CONFIRMED|UNVERIFIED]

**Where:** `path/to/file.py:123`
**Why it matters:** <the consequence, concretely>
**Evidence:** <the command output or code that proves it>
**Fix:** <the specific change>

## HIGH

### <one-line claim> [CONFIRMED|UNVERIFIED]

**Where:**
**Why it matters:**
**Evidence:**
**Fix:**

## MEDIUM

### <one-line claim> [CONFIRMED|UNVERIFIED]

**Where:**
**Why it matters:**
**Evidence:**
**Fix:**

## LOW

### <one-line claim> [CONFIRMED|UNVERIFIED]

**Where:**
**Why it matters:**
**Fix:**

## Refuted

Candidates that did not survive refutation, with the evidence that refuted them.
Recording these is what makes the absence of a finding look like work rather
than an oversight.

| Candidate | Refuted by |
|---|---|
| | |

## What is acceptable

- <what was checked and found sound>

## Required before approval

- [ ] <the change that must land>
