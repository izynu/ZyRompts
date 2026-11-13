# Acceptance tests: <feature name>

Spec: ./specification.md
Run: `<command that executes these checks>`

Every acceptance criterion from the specification appears here as a check.
UNVERIFIED is a legitimate outcome; rounding it up to PASS is not.

## Matrix

| ID | Criterion | Check | Expected | Actual | Result |
|---|---|---|---|---|---|
| AC1 | <from spec> | `<command>` | <expected> | <actual> | PASS |
| AC2 | <from spec> | `<command>` | <expected> | <actual> | FAIL |
| AC3 | <from spec> | `<command>` | <expected> | - | UNVERIFIED |

## Failures

### AC2 - <criterion>

**Observed:**
```text
<the actual output>
```
**Expected:** <the expected output>
**Cause:** <root cause, once known>
**Status:** open | fixed in <commit> | accepted as a known limitation

## Unverified

### AC3 - <criterion>

**Why it could not be checked:** <missing environment, unavailable service>
**What would check it:** <the check to run once the blocker is gone>

## Environment

- Commit: <sha>
- Platform: <os, runtime version>
- Date: <YYYY-MM-DD>
