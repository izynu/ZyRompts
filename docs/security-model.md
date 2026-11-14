# Security model

The model is small enough to state in full. Its central claim: **the controls
that matter are not prompts.** A model can be talked out of an instruction; it
cannot be talked out of a branch in `policy.py`.

## Trust boundaries

| Boundary | Untrusted side | Enforced by |
|---|---|---|
| Prompt -> agent | the user's text, pasted content | `classify.detect_injection`, intake rule |
| Tool output -> agent | file contents, web pages, command output | injection floor in `policy.evaluate` |
| Agent -> filesystem | the agent's chosen path | `check_path`, workspace containment |
| Agent -> shell | the agent's chosen command | `_HARD_DENY_COMMANDS` |
| Rule file -> dispatcher | a JSON file that may be edited | `validate_rule`, allowlisted handlers |
| Session -> session | a previous transcript | `redact_secrets` on every state and event-log write |

## The four layers

### 1. Hard denials (never allowed, at any autonomy)

Matched against the command string, before any autonomy band is consulted:

| Rule | Catches |
|---|---|
| `root-delete` | `rm -rf /`, `rm -rf ~` |
| `disk-overwrite` | `dd of=/dev/sd*` |
| `mkfs` | `mkfs.* /dev/*` |
| `fork-bomb` | `:(){ :\|:& };:` |
| `history-rewrite` | `git push --force` to a protected branch, `git filter-*`, `git reset --hard`, `git clean -fdx` |
| `credential-exfil` | `curl`/`wget` of `.ssh/id_*`, `.aws/credentials`, `.env` |
| `pipe-to-shell` | `curl ... \| sh` |
| `permission-nuke` | `chmod -R 777 /` |
| `sudo-anything` | any `sudo` |

`git reset --hard` is here rather than in ASK because it discards uncommitted
work with no recovery path. The right answer is "commit or stash first", not a
confirmation dialog the user will click through.

### 2. Protected paths

`check_path` denies writes to `/etc/passwd`, `/etc/shadow`, `/etc/sudoers`,
`~/.ssh/*`, `~/.aws/*`, `~/.config/gh/*`, `**/.git/config`, `/boot/*`,
`/dev/sd*`, and any path containing a null byte. With a workspace root set, a
write outside it is denied (`workspace-containment`).

### 3. The injection floor

Content that came from tool output or a fetched page is marked untrusted. An
untrusted call that would otherwise be ALLOW is capped at ASK, even under YOLO:

```python
if untrusted and verdict.decision is Decision.ALLOW:
    return Verdict(Decision.ASK, "untrusted content cannot escalate privilege",
                   "injection-floor")
```

The cap is a post-filter applied to the verdict of every branch in `evaluate`
and to both allow-list paths in `PolicyConfig.evaluate`, so a tool added later
cannot be born without it. An allow list says the operator trusts the *tool*;
it says nothing about the *content* of this call, which may have come from a
page or a tool result, so it does not lift the floor.

This is what makes "the web page told me to run this" a question rather than an
action.

### 4. Autonomy levels

| Level | Read tools | Safe mutations | Destructive | File writes |
|---|---|---|---|---|
| `read-only` | allow | ask | deny (hard table) | **deny** |
| `ask` (default) | allow | ask | deny (hard table) | ask |
| `auto` | allow | allow | deny (hard table) | allow |
| `yolo` | allow | allow | deny (hard table) | allow |

`read-only` denies writes outright rather than asking, because "ask" implies
"yes" is a valid answer, and one approval would negotiate the level away.

Unknown tools are treated as mutating: fail closed, not open.

## Secret handling

`redact_secrets` recognises OpenAI, Anthropic, GitHub, AWS, Slack and JWT
credentials, PEM private key blocks, and generic `password=...` /
`token: ...` assignments. It returns both the redacted text and the kinds found,
so a caller can log the fact of a secret without logging the secret.

```bash
zyrompts redact < output.log      # {"text": "...[REDACTED]...", "kinds": ["github_token"]}
```

The rule for agents: never paste a real credential into a report, a commit, or
a prompt. Redact, then name the location.

## The hook dispatcher as an attack surface

A hook runs with the user's privileges on every prompt, so its input is hostile
by assumption.

- **Rules are data.** `validate_rule` checks the event against
  `CAPABILITY_MATRIX`, the action type against the event's capability set, and
  that the rule has exactly one of `action` or `handler`.
- **Handlers are names.** `HANDLERS` and `MATCHERS` are dicts of functions; a
  rule can only name one that already exists. No `importlib`, no `getattr` on a
  dotted path, no `eval`.
- **Regexes are compiled defensively.** A bad pattern is a validation error, not
  a traceback at prompt time.
- **Every path exits 0.** A crash would block the prompt; silence does not.

## Prompt injection: what is and is not defended

**Defended deterministically:** instruction-like text in the prompt is flagged
(`detect_injection`) and the workflow drops to LIGHT so the agent reads before
it acts; untrusted tool output cannot escalate privilege; the security-review
skill reports embedded instructions rather than following them.

**Not defended by this repository:** the model's own judgement about ambiguous
content. A classifier reduces the attack surface; it does not eliminate the
class. Treat the injection floor as a seatbelt, not a guarantee.

## Reporting a vulnerability

See `SECURITY.md`. Do not open a public issue for a vulnerability that is
reachable in a default configuration.
