# ADR 0004: Hooks fail silent, not loud

Status: accepted
Date: 2026-11-13

## Context

A hook runs synchronously on the user's prompt. If it raises, the harness either
blocks the prompt or shows an error the user cannot act on. Both outcomes are
worse than the hook doing nothing, because the user came to type a prompt, not
to debug the framework.

## Decision

The dispatcher exits 0 on every path, and every failure degrades to an empty
result:

| Failure | Behaviour |
|---|---|
| unknown or missing event | exit 0, no output |
| unparsable or empty stdin | exit 0, no output |
| rules directory missing or empty | exit 0, no output |
| invalid rule file | skipped, noted in `validate`, never fatal at runtime |
| invalid regex in a rule | skipped, reported by `validate` |
| handler raises | caught, that rule contributes nothing |
| bypass prefix or machine event | exit 0, no output |

## Consequences

**Good**

- Installing the hooks cannot break the user's workflow.
- A broken rule is a `validate` failure in CI, not a runtime outage.

**Bad**

- A misconfigured hook is silent. If the rules directory path is wrong, nothing
  happens and nothing says so. The mitigation is `zyrompts health`, which
  reports rule and skill counts and fails when they are zero.
- Silent failure can hide a real defect in the engine itself. The mitigation is
  that the engine's logic is unit-tested directly, so the silent path is only
  the wiring.

## Alternatives rejected

**Fail loud.** One bad rule file would make every prompt error out. Unacceptable
for a tool that sits in front of every prompt.
