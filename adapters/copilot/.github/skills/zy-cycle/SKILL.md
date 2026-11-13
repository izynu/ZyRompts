---
name: zy-cycle
description: Draft, critique and merge a plan in one bounded loop, then stop for approval. Use when you want the whole planning loop in one pass without executing anything.
license: MIT
---

# Cycle

## Purpose

Run create -> critique -> merge repeatedly, within a hard bound, and stop at the
approval gate. This skill never executes the plan and never writes project code.

## Fixed rules

1. Never execute the plan or write project code in this run. The outputs are
   `plan.md`, `critique.md` and `cycle-log.md`.
2. The user owns the plan. Draft it only when it is empty or still the template.
   Never overwrite text the user wrote.
3. Never assume, ask. Merge automatically only when the change is obvious. Ask
   when a finding is ambiguous, touches a user-written requirement, changes scope,
   or conflicts with another finding.
4. Be adversarial in every iteration; report only findings that survive refutation.
5. Grade confidence per finding and prove each with evidence.
6. Re-read `plan.md` from disk at the start of each iteration.
7. Verify what you merge: run any command before writing it into a verification
   section. Read-only commands only.
8. Never merge silently. Log every merged, asked and skipped finding.
9. Stop early when an iteration surfaces no new findings.
10. Be brief. No filler, no emoji, no em dashes.

## Procedure

1. Load config from `.zyrompts/config.json`; default `plansFolder` to
   `.zyrompts/plans` and `cycleIterations` to 3, clamped to 1-5.
2. Select or create the plan folder for the given name.
3. If `plan.md` is empty or still the template, research the codebase and draft it.
4. Loop up to `cycleIterations` times:
   - Re-read `plan.md`.
   - Critique per the `critique` skill; write `critique.md` with the incremented
     iteration number.
   - If nothing new, stop.
   - Merge obvious CONFIRMED findings; ask about the rest, grouped into one call.
   - Append to `cycle-log.md` and print the same summary.
5. Print the final plan and the open items.
6. Stop at the approval gate:

```
Cycle complete after N iteration(s): <path>
Merged: X findings. Asked about: Z. Not merged: Y.
Nothing has been executed and no project code was changed.
Review the plan. When you approve it, run /zy-execute.
```

## Failure handling

- Iteration limit reached with findings open: list them as open items, do not
  force a merge.
- The plan needs splitting: record the recommendation, do not split it yourself.
- A merge would lose user text: ask instead of merging.

## Evaluation cases

- Empty plan -> drafted, critiqued, merged, approved in one run.
- Plan with a user-written constraint -> constraint preserved, findings touching
  it asked about rather than merged.

## Version

1.0.0. Depends on: plan, critique. Platforms: all.
