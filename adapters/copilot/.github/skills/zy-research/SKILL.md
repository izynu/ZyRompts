---
name: zy-research
description: Gather evidence from the codebase, docs and web, and return conclusions with citations and a confidence score. Use when a task needs facts you do not have, when comparing options, or when the answer depends on current external behavior.
license: MIT
---

# Research

## Purpose

Answer a question with evidence, not with plausible recall. The deliverable is a
short report where every claim has a source, every source has a reliability tier,
and the confidence is stated rather than implied.

## Activation

- The task needs facts about a library, API, version, or external system.
- The user asks to compare, investigate, or find out.
- A plan depends on an assumption that has not been checked.

## Procedure

1. Write the question as one sentence, and the sub-questions needed to answer it.
2. Search in reliability order: the repository itself, then official docs, then
   primary sources (source code, changelogs), then secondary, then community.
   Stop as soon as the question is answered; do not collect for its own sake.
3. For each finding, record: the claim, the source, the tier, the retrieval date.
   A finding without a source is not a finding.
4. Cross-check. Two independent sources agreeing raises confidence; two
   disagreeing caps it. State the disagreement rather than resolving it silently.
5. Check freshness. A two-year-old answer about a fast-moving library is a lead,
   not a fact.
6. List the gaps: what you could not answer, and why.
7. Score confidence using source tier, corroboration, diversity and staleness.

## Output format

```
# Research: <question>
Confidence: <0.0-1.0> (<freshness>)

## Findings
- [official] <claim>
  - source: <url or file:line>

## Gaps
- <what could not be answered and why>
```

## Failure handling

- No reliable source exists: report confidence near zero and say what would raise
  it. Do not promote a blog post to a fact.
- Sources conflict: report both, name the likely cause, and recommend the check
  that would settle it.
- The question is really a design decision: hand off to `brainstorm` or `plan`.

## Evaluation cases

- "does library X support Y?" -> official docs citation, version noted, freshness
  stated.
- "why is this slow?" -> codebase evidence first, not a generic performance essay.

## Version

1.0.0. Depends on: none. Platforms: all.
