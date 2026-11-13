# Reports

`zyrompts eval` prints a per-suite pass rate and the failing cases. This
directory is where a report is kept when one is worth keeping.

Reports are not committed on every run; a report is committed when it records a
decision, a regression, or a baseline that a later change is compared against.

## Naming

```
YYYY-MM-DD-<scope>-<short-sha>.md
2026-11-13-release-0.1.0.md
2026-11-20-policy-regression.md
```

## What a report contains

```markdown
# Eval report: <scope>

Date: <YYYY-MM-DD>
Commit: <sha>
Python: <version>

## Result

| Suite | Passed | Total | Rate |
|---|---|---|---|
| classification | 25 | 25 | 100% |
| policy | 27 | 27 | 100% |
| prompt_score | 12 | 12 | 100% |
| injection | 18 | 18 | 100% |

## Failures

None.

## Notes

- What changed since the previous report.
- Any case whose expectation was corrected rather than the code.
```

## Correcting a case, not the code

When a case fails, there are two possibilities and they are not symmetrical:

- **The code is wrong.** Fix the code; the case stays.
- **The expectation was wrong.** Fix the case, and say in the report that you
  did, with the reason. A dataset that is quietly edited to go green is worse
  than a red suite.

Every expectation corrected during 0.1.0 development is listed in
`CHANGELOG.md` under "Fixed during development" so the corrections are visible.

## Baseline

The 0.1.0 baseline is 82/82 across four suites. A change that drops any case is
a regression until proven otherwise.
