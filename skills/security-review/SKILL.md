---
name: security-review
description: Audit a change or codebase for security defects, using deterministic checks first and reasoning second. Use when code handles untrusted input, auth, secrets, files, or the network.
allowed-tools: Read, Glob, Grep, Bash
argument-hint: path, diff, or component to audit
depends-on: code-review
---

# Security Review

## Purpose

Find the defect an attacker would find first. The review is threat-model driven:
name the trust boundary, then ask what crosses it unchecked.

## Activation

- Code parses untrusted input: HTTP, files, CLI arguments, environment, webhooks.
- Code makes an authorization or authentication decision.
- Code handles credentials, tokens, keys or personal data.
- Before any release, and after any change to the above.

## Deterministic first

Run the mechanical checks before reasoning, because a model can be talked out of
an instruction and cannot be talked out of a Python `if`:

```bash
zyrompts policy "<command>" --autonomy ask   # hard-deny table, protected paths
zyrompts redact < file                       # secret patterns in output
zyrompts diff-review <diff>                  # eval/exec, hardcoded creds, bare except
```

Then grep for the classes the checks cannot see:

- String-built SQL, shell, LDAP or template input.
- Path joins with user-controlled segments (traversal, symlink following).
- `pickle`, `yaml.load`, `eval`, `exec`, `subprocess` with `shell=True`.
- Authorization checks that run after the action, or only in the UI layer.
- Secrets in logs, error messages, or URLs.

## Procedure

1. Draw the trust boundary. What is attacker-controlled, and where does it enter?
2. For each entry point, follow the value to its sinks: query, file, process,
   template, redirect, deserializer, response.
3. Check each sink for the four failures that cause most real breaches:
   - Injection: the value is concatenated into a language, not passed as data.
   - Broken access control: the object is fetched by id without an owner check.
   - Credential exposure: the secret reaches a log, a URL, or a client.
   - Unsafe deserialization or file write: attacker input chooses the target.
4. Check the failure path: does an error reveal internals, or fail open?
5. Grade with the `code-review` severities. A security finding is `CRITICAL` when
   it is reachable by an unauthenticated attacker, `HIGH` when authenticated.
6. Write the exploit path, not just the weakness: the request, the state, the
   result. A finding without a path is a hypothesis, and is marked `UNVERIFIED`.

## Rules

- Never test against a system you were not explicitly authorised to test.
- Use read-only checks against live systems. Do not run exploit payloads without
  explicit approval and a named target.
- Redact every secret you encounter in output: show `sk-...abcd`, never the value.
- Never weaken a control to make a test pass.
- A theoretical finding with no reachable path is reported as INFO, not HIGH.

## Output format

```
VERDICT: BLOCK | REVISE | PASS
## <SEVERITY> - <class> - <location> [CONFIRMED|UNVERIFIED]
Boundary: <what is attacker-controlled>
Path: <entry point -> sink>
Impact: <what an attacker gains>
Evidence: <request, command, or file:line>
Fix: <the control that closes it>
```

## Failure handling

- Cannot reach the live system: audit statically and label reachability `UNVERIFIED`.
- The finding needs a product decision (for example, who may read a record):
  report it as a question, do not guess the intended policy.
- A dependency is vulnerable but not reachable: report it, and say it is not
  reachable, so it is not fixed at the wrong priority.

## Evaluation cases

- `SELECT * FROM t WHERE id='{uid}'` -> CRITICAL injection, CONFIRMED.
- Fetch-by-id with no owner check -> HIGH broken access control.
- `print(os.environ)` in a startup log -> HIGH credential exposure.
- `yaml.load(f)` with a `safe_load` alternative -> HIGH unsafe deserialization.

## Version

1.0.0. Depends on: code-review. Platforms: all.
