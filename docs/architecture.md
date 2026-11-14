# Architecture

ZyRompts is a small deterministic core with declarative configuration around it.
The rule that shapes every decision: **behaviour that must hold is Python;
behaviour that guides is data.**

```
                    +-----------------------+
   user prompt ---> |  hooks/rules/*.json   |  declarative nudges
                    +-----------+-----------+
                                | loaded by
                    +-----------v-----------+
                    |  hooks.py dispatcher  |  one entry point per event
                    +-----------+-----------+
                                | handlers.py (allowlist)
                    +-----------v-----------+
                    |     core/zyrompts     |
                    |  classify  prompts    |
                    |  policy    review     |
                    |  workflow  state      |
                    |  research  decorum    |
                    |  agents    telemetry  |
                    +-----+-----------+-----+
                          |           |
             +------------v--+     +--v-------------+
             |   cli.py      |     |  adapters.py   |
             | the commands  |     | 5 platforms    |
             +---------------+     +----------------+
```

## Layers

### 1. Canonical source

- `skills/<name>/SKILL.md`: the skill contracts. Frontmatter carries `name`,
  `description`, `allowed-tools`, `argument-hint`, `depends-on`,
  `optional-depends-on`. The body is the procedure.
- `agents/<role>.md`: written contracts for six of the thirteen roles.
  Frontmatter mirrors `agents.py:REGISTRY`; a parametrised test checks each
  file against the registry and fails if the two drift.
- `hooks/rules/<Event>/*.json`: one rule per file.

Everything else is generated or derived.

### 2. The engine (`core/zyrompts/`)

No third-party imports, so it runs inside a hook, a CI job, or an air-gapped
machine with only Python 3.9+.

| Module | Responsibility | Key invariant |
|---|---|---|
| `classify.py` | intent, complexity, tier, injection signals | a code-changing request with no anchor is never DIRECT |
| `prompts.py` | score 0-100, framework choice, rewrite | an explain request is not graded on success criteria |
| `policy.py` | autonomy levels, hard denials, redaction | hard denials fire under YOLO |
| `hooks.py` | rule loading, validation, priority merge | exit 0 on every path |
| `handlers.py` | named handlers and matchers | string names only, never `eval`/`importlib` |
| `state.py` | project state + JSONL log | atomic write; schema downgrade refused |
| `workflow.py` | phases, gates, bounded loops | a block records where to resume |
| `review.py` | plan/spec/diff critique | a finding is reported only after refutation |
| `research.py` | source tiering, confidence | confidence needs evidence, not vibes |
| `agents.py` | roles, delegation, scheduling | no agent reviews its own output |
| `adapters.py` | canonical -> platform renderers | pure functions; no I/O except `write()` |
| `evals.py` | JSONL datasets, evaluators | one failing case does not stop the suite |
| `decorum.py` | the behaviour policy, plus a checker | claims without evidence are flagged |
| `telemetry.py` | cost and duration accounting | priced by tier, not by product name |
| `cli.py` | the command line | every capability scriptable without a model |

### 3. The hook engine

`hooks.py` loads every rule, validates it against `CAPABILITY_MATRIX`, evaluates
the criteria against the payload, and merges the matching fragments by
`priority` (lower number runs first). Three design choices are load-bearing:

**Handlers are named, not imported.** A rule says `"handler": "intake"`, and the
dispatcher looks the name up in `HANDLERS`. There is no path-based import, no
`getattr`, no `eval`. A rule file is data even if an attacker controls it.

**The dispatcher never fails loudly.** Missing event, unparsable stdin, unknown
rule, bad regex: each returns an empty result and exit 0. A hook that crashes
blocks the user's prompt, which is worse than a hook that does nothing.

**Bypass is a contract, not a suggestion.** `*` skips, `#` memorises, `/` is a
slash command, and harness machine events (`<task-notification>`,
`<system-reminder>`, `<command-name>`, `<local-command-stdout>`) are all silent.
`handlers.py` mirrors the engine's own check, and `tests/test_hooks.py` pins
both, so a handler-backed rule cannot diverge from an action-backed one.

### 4. Adapters

An adapter is a pure function from `list[SkillMeta]` to `dict[path, content]`.
`AdapterResult.write()` is the only I/O. That makes the generated trees
byte-reproducible, and `scripts/generate-adapters.py --check` turns drift into a
CI failure rather than a review comment.

### 5. The lifecycle

```
INTAKE -> CLARIFY -> RESEARCH -> SPECIFY -> PLAN -> CRITIQUE -> APPROVE
       -> IMPLEMENT -> REVIEW -> FIX -> VERIFY -> ARCHIVE -> DONE
```

Four tiers select a subsequence of that chain:

| Tier | Phases | Selected when |
|---|---|---|
| DIRECT | INTAKE, DONE | trivial ask, or a question about code |
| LIGHT | INTAKE, IMPLEMENT, VERIFY, DONE | small, contained change |
| PLANNED | INTAKE, CLARIFY, SPECIFY, PLAN, CRITIQUE, APPROVE, IMPLEMENT, REVIEW, VERIFY, DONE | moderate build/refactor |
| FULL | all phases | large, wide, or architectural |

The tier is a **floor**, never a ceiling: the classifier raises a tier on
evidence and never lowers a heavier one. A blocked phase records `resume_at`, so
the workflow stays blocked until the gate is met instead of skipping forward.

### 6. State

`StateStore` writes `.zyrompts/state/project.json` atomically (`mkstemp` +
`fsync` + `os.replace`) and appends to `.zyrompts/state/events.jsonl`. The state
file carries a `version`; loading a newer version raises rather than silently
dropping fields the running code does not understand. Unparsable JSON degrades
to a fresh state, with the broken file moved aside so the next save cannot
overwrite the only copy.

## Data flow, end to end

1. `UserPromptSubmit` fires. The dispatcher loads `intake`, which calls
   `classify()` and injects the tier, the intent, and the first phase.
2. The agent follows the named skill. Each skill's Procedure is the contract.
3. Before every mutating tool, `PreToolUse` fires. `policy.evaluate()` returns
   ALLOW / ASK / DENY, with the rule that fired.
4. On `Stop`, `verify_stop` checks a completion claim against evidence in the
   transcript and injects the missing proof.
5. `archive` writes the handoff; `state.py` records the decision.

## Extending it

| Want to change | Where | Rebuild needed |
|---|---|---|
| A nudge's wording or trigger | `hooks/rules/<Event>/*.json` | no |
| A skill's procedure | `skills/<name>/SKILL.md` | `adapters --write` |
| A platform's output format | `adapters.py` renderer | `adapters --write` |
| A policy rule | `policy.py` tables | no |
| A lifecycle gate | `workflow.py` | no |
| An eval expectation | `evals/datasets/*.jsonl` | no |

## Why no framework

The core is a few thousand lines of standard library. A dependency-free core is
what makes the hooks safe to install, the evals fast enough to run on every
commit, and the behaviour reproducible on a machine with no network.
