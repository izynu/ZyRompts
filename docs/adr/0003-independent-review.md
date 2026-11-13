# ADR 0003: Independent review is structural, not advisory

Status: accepted
Date: 2026-11-13

## Context

"Have a different agent review the work" is a common instruction and a weak one.
An agent asked to review its own output grades it against its own assumptions,
and a single-agent loop that both writes and reviews converges on "looks good".

## Decision

Make independence a property of the orchestrator, not of the instructions.

- Every `AgentSpec` declares `can_review` — the roles whose output it may judge.
- `Orchestrator.review_pairs()` returns a `(producer, reviewer)` pair for every
  completed delegation, choosing a reviewer that is **not** the producer's role.
- `next_batch()` never schedules a writer concurrently with anything else: a
  batch containing any non-read-only delegation is capped at one.
- An agent with no declared reviewer gets the verifier, which is a different
  role by construction.

## Consequences

**Good**

- Self-review is impossible through the orchestrator's API, not merely
  discouraged.
- The scheduler cannot produce the classic race where a reviewer reads a file
  the writer is still editing.

**Bad**

- Throughput is lower: writers are serialised by design.
- The registry must be maintained. A new role with no `can_review` silently
  falls back to the verifier, which is safe but may be the wrong judge.

## Alternatives rejected

**Prompt instruction.** "Do not review your own work" is exactly the kind of
rule a model can be talked out of. This is the ADR that most directly applies
ADR 0001.
