---
name: archive
description: Close out a piece of work so it can be resumed or handed over without the original conversation. Use at the end of a plan, or when work is paused.
allowed-tools: Read, Write, Glob, Bash
argument-hint: plan slug or task
---

# Archive

## Purpose

Make the work self-describing. Someone with the archive and no memory of the
session should know what was built, what was decided, what is still broken, and
what to do next.

## Procedure

1. Create `.zyrompts/archive/<slug>-<YYYYMMDD-HHMMSS>/`. The timestamp makes
   archives immutable: a second archive never overwrites the first.
2. Copy in, or write fresh:
   - `plan.md`, `critique.md`, `execution-log.md`, `cycle-log.md` if present.
   - `state.json`, the final project state snapshot.
   - `verification.md`, the `verify` table with its evidence.
   - `review.md`, surviving findings and their status.
3. Write `HANDOFF.md` with these sections, and nothing else:
   - What this work was for, in two sentences.
   - What is done, as a list of completed items.
   - What is not done, as a list, with the reason each is open.
   - Decisions made, each with its rationale and the alternative rejected.
   - Known issues, each with severity and a `file:line` where known.
   - The exact command to run to pick the work back up.
4. Record the git commit, if the work was committed, and the branch.
5. Update `.zyrompts/state/project.json`: phase `archived`, and clear the
   `next_task` pointer.
6. Print the archive path.

## Rules

- The archive is append-only. Never edit a past archive; write a new one.
- No secrets in the archive. Redact before copying logs.
- No placeholders. "TBD" in a handoff is a lie about completeness.
- Keep it short enough to read. A 2000-line handoff is not a handoff.

## Output format

`HANDOFF.md` follows the section list in step 3 exactly, so two archives can be
diffed against each other.

## Failure handling

- A required input file is missing: write the section as "not recorded", and say
  which file was expected. Do not reconstruct it from memory as if it were fact.
- The work is mid-step: archive anyway, and put the partial step and its exact
  state in "What is not done".
- Uncommitted changes exist: record them, do not commit them unless asked.

## Evaluation cases

- A completed plan -> full archive, all six sections, resume command present.
- An abandoned plan -> archive with the reason for abandonment and the state.
- A second archive of the same slug -> a new timestamped directory, first intact.

## Version

1.0.0. Depends on: verify. Platforms: all.
