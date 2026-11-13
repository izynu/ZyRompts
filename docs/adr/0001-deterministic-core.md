# ADR 0001: Deterministic core, declarative configuration

Status: accepted
Date: 2026-11-13

## Context

The three projects this framework draws from solve the same problem differently.
prompt-master encodes knowledge as prose. plan-critique-skills encodes process as
prose. claude-code-prompt-improver encodes triggers as JSON, but the behaviour
behind each trigger is Python.

The question: should the whole framework be prompt text, or should the rules
that matter be code?

## Decision

Split by enforceability.

- A rule that **must** hold is a deterministic check in `core/zyrompts/`, or a
  declarative rule the engine evaluates.
- A rule that **guides** judgement is prompt text in a skill or the decorum
  policy.

The split is visible in the repository: `policy.py` hard-denies `rm -rf /`;
`skills/verify` says "run the check before claiming success" in prose.

## Consequences

**Good**

- Security controls cannot be prompted away. The hard-deny table fires at every
  autonomy level including YOLO, because it is a `for` loop.
- Behaviour is testable. The suite pins what prose can only assert.
- Evals can regress. A prompt-only rule that stops working is invisible; a rule
  with an eval case that starts failing is a red build.

**Bad**

- Prose rules still matter and are still unenforceable. The decorum policy's
  "never agree to be agreeable" has no test, and cannot have one.
- The split costs a design decision per rule: is this a guarantee or a guide?
  Getting it wrong in the "guide" direction is the common failure, and it is how
  prompt-only frameworks drift.
- More code to maintain than a prompt library.

## Alternatives rejected

**All prose.** Cheaper to write, impossible to test, and the security properties
become suggestions. Rejected because a framework whose selling point is
discipline cannot make discipline advisory.

**All code.** Would require the agent to call a tool for every judgement, which
is slow and brittle. Judgement belongs to the model; the decision was only that
*guarantees* do not.
