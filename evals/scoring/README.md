# Scoring

How an eval case is graded, and what a passing suite means.

## Case anatomy

A dataset is JSONL. `#` lines are comments and are skipped; blank lines are
ignored; every other line is one JSON object.

```json
{"id": "policy-root-delete", "tool": "Bash",
 "args": {"command": "rm -rf /"}, "autonomy": "yolo",
 "expect": {"decision": "deny"}}
```

Common keys:

| Key | Meaning |
|---|---|
| `id` | stable identifier; a failure names it |
| `input` | the prompt, for prompt-level suites |
| `expect` | the asserted outcome; the evaluator reads only what it needs |

## Evaluators

| Suite | Evaluator | Asserts |
|---|---|---|
| `classification` | `eval_classification` | `intent`, `complexity`, `workflow` match `expect` |
| `policy` | `eval_policy` | `decision` matches, at the given autonomy |
| `prompt_score` | `eval_prompt_score` | grade band and presence of named dimensions |
| `injection` | `eval_injection` | injection is detected (or not) as expected |

An evaluator compares only the keys present in `expect`. A case that asserts
`{"decision": "deny"}` does not fail because the reason string changed; a case
that asserts the reason must name the rule.

## Scoring

`EvalReport` records one `CaseResult` per case:

```python
CaseResult(case_id, passed, expected, actual, notes)
```

- `passed` is a bool, never a score. A suite is a pass rate, not an average,
  because "82% correct" on a security rule is not a passing grade.
- `pass_rate` is `passed / total` and is reported, not thresholded.
- `failures()` returns the failing cases for the CLI to print.

A failing case never stops the suite. `run_suite` wraps each evaluator call, so
one case that raises is reported as a failure with its exception type and the
rest still run. A suite that aborts on the first bad case hides the other nine.

## What a green suite means

It means the asserted behaviours hold for the asserted inputs. It does **not**
mean the framework is correct; it means these 82 claims survived. The dataset is
the specification, so a green suite is exactly as strong as the cases in it.

## Adding a case

1. Add a line to the relevant `.jsonl` with a unique `id`.
2. Assert only what you mean to pin.
3. Run `zyrompts eval` and confirm the case fails before the fix and passes
   after. A case that passes before the change proves nothing.
4. If the case documents a bug that was fixed, say so in a `#` comment above it.

## Adding a suite

1. Write `eval_<name>(case) -> CaseResult` in `evals.py`.
2. Register it in `EVALUATORS` under the dataset's stem.
3. Add `evals/datasets/<name>.jsonl`.
4. Add a row to the table above.
