# ADR 0002: Cheap by default, never cheap enough to be wrong

Status: accepted
Date: 2026-11-13

## Context

A 24-step lifecycle applied to every request is unusable: "what does this
function do" would require a specification and a critique. A framework that
forces the full process on trivial work gets switched off, and then the process
is not there when it matters.

The opposite failure is worse: a classifier that calls everything trivial, so
the heavy machinery never runs.

## Decision

Four tiers, chosen by evidence, with a floor that only ever raises.

| Tier | Phases |
|---|---|
| DIRECT | INTAKE, DONE |
| LIGHT | INTAKE, IMPLEMENT, VERIFY, DONE |
| PLANNED | INTAKE, CLARIFY, SPECIFY, PLAN, CRITIQUE, APPROVE, IMPLEMENT, REVIEW, VERIFY, DONE |
| FULL | all 13 |

Each tier is a subsequence of the full chain, not a prefix: DIRECT ends at DONE
and LIGHT skips RESEARCH, SPECIFY, PLAN, CRITIQUE and APPROVE.

Two floors, each added after the first version got it wrong:

1. **A code-changing intent with no concrete anchor is at least LIGHT.**
   "fix the bug" has no file, no error, no identifier. It is not a one-line
   edit; it is an underspecified request.
2. **A terse request with wide scope is not trivial.** "migrate the monolith to
   microservices" is five words and a quarter of work. The architectural cues
   raise complexity regardless of length.

The tier is a floor, not a ceiling: `choose_workflow` computes the tier from
intent and complexity first, then applies the no-anchor floor only when the
result would be DIRECT.

## Consequences

**Good**

- A one-line question stays one line.
- The two failures that matter are pinned by eval cases, so a future change to
  the cue tables cannot silently regress them.

**Bad**

- The classifier is a heuristic. A request phrased unusually can be graded
  LIGHT when it deserved PLANNED. The mitigation is that the tier is visible in
  the injected context and the user can say "plan this properly".
- Cue tables need maintenance. A new domain (say, data pipelines) needs its own
  cues or it will be graded by generic complexity only.

## Alternatives rejected

**Always PLANNED.** Safe and unusable.

**Model-decided tier.** The model already decides everything else; making the
cheapest decision the least deterministic one defeats the purpose.
