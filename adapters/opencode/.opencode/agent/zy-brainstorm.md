---
description: Explore the option space before committing to an approach. Use when the user has a goal but no decided solution, asks for ideas or alternatives, or when a single approach would be premature.
mode: subagent
tools: Read, Glob, Grep
---

# Brainstorm

## Purpose

Widen the option space cheaply, then narrow it with evidence. The deliverable is
a short list of genuinely different approaches with tradeoffs, not a long list of
variations on one idea.

## Activation

- The user asks for ideas, options, or alternatives.
- A problem has more than one plausible shape and the cost of choosing wrong is
  high.
- A plan is being written before the approach is settled.

## Procedure

1. Restate the goal in one sentence and the constraints in a short list. If the
   goal is unclear, use the `clarify` skill first.
2. Inspect what already exists: prior art in the repo, related code, existing
   dependencies. Do not brainstorm what is already built.
3. Generate 3-5 distinct approaches. Distinct means they differ in structure or
   tradeoff, not in naming. For each, write: the shape in one line, what it costs,
   what it makes easy, what it makes hard, and when it fails.
4. Name the approach you would choose and why, in two sentences. If you would not
   choose any, say what is missing.
5. Stop. Do not implement.

## Output format

```
## Goal
<one sentence>

## Options
### 1. <name>
- Shape: ...
- Cost: ...
- Easier: ...
- Harder: ...
- Fails when: ...

## Recommendation
<approach>, because <reason>. The main risk is <risk>.
```

## Failure handling

- Fewer than three genuinely distinct options exist: say so and recommend the one
  you have rather than padding the list.
- The options differ only in style: collapse them and state the real decision.
- A constraint rules out every option: surface the constraint as the problem.

## Evaluation cases

- "how should we add search?" -> 3 options across DB full-text, a search service,
  and in-memory, with cost and scale tradeoffs.
- "ideas for the onboarding flow" -> 3 distinct flows, not 3 color schemes.

## Version

1.0.0. Depends on: clarify (optional). Platforms: all.
