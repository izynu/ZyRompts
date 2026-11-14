# Security policy

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x | yes |

## Reporting a vulnerability

Report privately, not in a public issue.

- Use GitHub's private vulnerability reporting on this repository
  (Security -> Report a vulnerability).

Include: the version, the configuration, the exact steps to reproduce, and the
impact you believe it has. A proof of concept helps; a weaponised one does not
belong in the report.

**Do not** include real credentials in a report. If a credential is part of the
finding, say where it is and redact its value.

## What counts as a vulnerability here

The framework's attack surface is specific, so the list is explicit:

**In scope**

- A tool call that bypasses a hard denial in `policy.py` (for example, a
  destructive command that is allowed under `yolo`).
- A write that escapes the workspace root, or reaches a protected path.
- A way for untrusted tool output or fetched content to escalate privilege past
  the injection floor.
- A hook rule that can execute arbitrary code through the rule file: for
  example, a handler name that resolves to an import or `getattr` on a path.
- A redaction bypass: a credential pattern that `redact_secrets` misses in a
  common format.
- A crash or traceback in the hook dispatcher that blocks a user's prompt.

**Out of scope**

- A prompt that persuades a model to misbehave. That is the model's judgement,
  and this repository reduces the surface; it does not eliminate the class.
- Findings that require the attacker to already have write access to the rules
  directory or the Python source. At that point the attacker is the operator.
- Denial of service through deliberately enormous input.
- Anything in `adapters/`, which is generated build output.

## Response

| Stage | Target |
|---|---|
| Acknowledge | 3 working days |
| Triage and severity | 7 working days |
| Fix for a reachable issue in a default configuration | 30 days |
| Public disclosure | coordinated, after the fix ships |

## Hardening checklist for operators

- Run with `--autonomy ask` or `read-only` unless you have a reason not to.
- Set a workspace root so containment is enforced.
- Run `zyrompts health` and `zyrompts validate` after any rule change.
- Treat a rule file as code: review it before installing it.
- Keep the Python runtime patched; the core has no third-party dependencies,
  so the interpreter is the dependency.
