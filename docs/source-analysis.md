# Analysis: the three source repositories

What each downloaded project does, how it works underneath, and what was taken
into ZyRompts. Every claim below was checked against the source, not inferred
from the README.

---

## 1. `prompt-master-main`

**Size.** ~1,490 lines of markdown: `SKILL.md` (499), `README.md` (423),
`references/templates.md` (483), `references/patterns.md` (82). No executable
code.

**What it is.** A prompt-engineering skill. Its frontmatter is unusually
precise about activation: it fires *only* when the user explicitly asks to
write, fix, improve or adapt a prompt for a specific tool, and explicitly does
not fire for general conversation or coding work. That activation discipline is
the first thing worth copying.

**How it works in the backend.** There is no runtime. The structure is the
mechanism:

- A **PRIMACY ZONE** at the top holds identity, hard rules and the output lock.
  Primacy matters because a long markdown file is read in order and the model
  weights the opening most heavily.
- **Hard rules** are stated as prohibitions with reasons: never output a prompt
  without confirming the target tool; never request hidden chain-of-thought;
  never ask more than three clarifying questions; never pad.
- It ranks techniques by fabrication risk in a single prompt: role assignment,
  few-shot and explicit verification are preferred; Mixture of Experts, Tree of
  Thought, Graph of Thought and Universal Self-Consistency are flagged as high
  risk unless explicitly requested, because they simulate machinery that is not
  actually there.
- An **output lock** fixes the response shape (one copyable block, a one-line
  rationale, optional setup note).

**What it is good at.** Knowing which techniques are theatre. The
fabrication-risk ranking is the most valuable single page in the three repos.

**Where it stops.** Nothing verifies that the produced prompt is better. The
"improvement" is the model's judgement, so it is neither reproducible nor
regressable.

**What ZyRompts took.** The vocabulary (RTF, CO-STAR, RISEN, CRISPE) and the
anti-pattern spirit, made deterministic: `prompts.py` scores seven weighted
dimensions, picks a framework, rewrites, and `evals/datasets/prompt_score.jsonl`
pins the grade bands. `model_notes` carries the per-family guidance that
prompt-master spreads across prose.

---

## 2. `plan-critique-skills-main`

**Size.** Five skills (`create`, `critique`, `cycle`, `execute`, `archive`),
each with a format reference (`plan-template.md`, `critique-format.md`,
`cycle-log-format.md`, `execution-log-format.md`, `execution-state-format.md`),
a shared `working-agreement.md`, per-platform docs for Claude Code, Agy (Gemini
CLI) and GitHub Copilot CLI, and a CI script.

**What it is.** A plan → critique → execute → archive workflow, distributed as a
Claude Code plugin and as plain skills for the other two platforms.

**How it works in the backend.** Two mechanisms worth naming:

1. **A configuration file drives the loop.** `.claude/plan-critique-config.json`
   holds `plansFolder`, and `cycle` reads an optional `cycleIterations` from the
   same file: default 3, clamped to 1-5. So the bound is not only a sentence in
   the prompt; it is a value read from disk and clamped in code-free prose. It
   also stops early when an iteration surfaces no new findings.
2. **A shared working agreement is referenced by path.** Every skill points at
   `working-agreement.md` with a fallback search order (project root, then
   `.claude/`), and says what to do when it is missing. That is a deliberate
   answer to the "the instruction file was not loaded" failure.

The `cycle` skill's fixed rules are the strongest writing in the three repos:
never execute during planning; the user owns `plan.md` and it must not be
overwritten; never assume, ask; be adversarial every iteration; grade
CONFIRMED only against the codebase, otherwise UNVERIFIED with what could not be
checked; re-read `plan.md` from disk each iteration because merging shifts line
numbers.

**What it is good at.** The review discipline and the line-number rule. "Re-read
from disk, cite only from that copy" prevents a whole class of stale-citation
errors that most planning prompts never consider.

**Where it stops.** The iteration count and the confidence grades are still
executed by the model following prose. The repo validates its Copilot skill
manifests in CI (`scripts/validate-copilot-skills.sh`), but it does not test the
loop behaviour itself.

**What ZyRompts took.** The whole cycle, with the bound moved into code:
`workflow.loop_critique` (3) and `loop_fix` (2) are counters, and exceeding one
blocks the phase rather than looping. `review.py` requires refutation before a
finding is reported, grades CONFIRMED/UNVERIFIED, and adds the deterministic
checks (missing affected files, missing verification, non-existent paths). The
re-read-from-disk rule is honoured by `critique_plan` operating on the text it is
given, never on a cached copy.

---

## 3. `claude-code-prompt-improver-main`

**Size.** A Python hook engine (`scripts/engine.py`, `scripts/rules.py`,
`scripts/nudge_builtins.py`), nine nudge rules under
`nudges/<EventName>/*.json`, `hooks/hooks.json`, and about 1,560 lines of tests
across six files.

**What it is.** A declarative hook engine for Claude Code that injects context
at `UserPromptSubmit`, `PreToolUse` and `SubagentStart`. Nine nudges, each
firing only when it applies: clarity (`improve`), approach assessment,
workflow/plan-first, output readability, ask-user-question, plan mode, plan
writing, background execution, and subagent routing.

**How it works in the backend.** This is the most engineering-complete of the
three, and the architecture is the contribution:

- `engine.py <EventName>` reads the hook JSON on stdin once, runs the event's
  rules, merges `inject_context` fragments by priority with a blank-line join,
  emits one `hookSpecificOutput`, and exits 0 on every path. A missing or
  unknown event is a clean no-op that never reads stdin.
- `rules.py` owns the loader, `validate_rule`, the `CAPABILITY_MATRIX`, and
  `rules_for(event)`. Rules live in per-event directories whose parent must
  match the rule's `event` field. Invalid rows are skipped with a stderr note;
  loading never raises into the engine.
- Regexes are compiled once per dispatched event, not at load, so an event with
  no rules costs nothing.
- `_read_payload` decodes bytes as UTF-8 explicitly, because text-mode stdin
  uses the Windows code page and garbles non-ASCII.
- Two nudges evaluate every prompt (`improve`, `plan-mode`); the other seven are
  keyword- or exactly-gated so a false fire is cheap to dismiss.

**What it is good at.** The shape. One dispatcher, a JSON registry, priority
merge, a clean no-op, and a rule validator with a capability matrix. It also
shows that the engine can be tested, which the other two do not.

**Where it stops.** It only nudges prompts. There is no policy, no lifecycle, no
review, no state, and no cross-platform generation.

**What ZyRompts took.** The architecture, generalised and hardened. `hooks.py`
mirrors `engine.py` (stdin-once, priority merge, exit 0 everywhere, nested
`match_target` paths); `hooks/rules/<Event>/*.json` mirrors `nudges/`;
`handlers.py` holds the named behaviours; `CAPABILITY_MATRIX` is carried over
almost verbatim. Three properties were hardened beyond the original:

1. **Handlers are names, never imports.** A rule can only name a function that
   exists in `HANDLERS`. No path-based import, no `getattr`, no `eval`.
2. **Validation is a CLI command, not only a runtime skip.** `zyrompts validate`
   checks every rule, so a typo is a red build rather than a stderr line nobody
   reads.
3. **Bypass is a shared contract.** The engine and the handlers use one
   definition (`*`, `#`, `/`, harness machine events), so a handler-backed rule
   cannot diverge from an action-backed one. This was a real bug found by a
   test, not a design intention.

---

## How the three combine

| Concern | Source | ZyRompts implementation |
|---|---|---|
| Prompt knowledge and anti-patterns | prompt-master | `prompts.py` (deterministic scoring and rewriting) |
| Planning discipline and review grading | plan-critique-skills | `workflow.py` + `review.py` (counters, refutation, verdicts) |
| Nudge engine and rule registry | prompt-improver | `hooks.py` + `hooks/rules/` |
| Activation discipline | prompt-master | precise `description` fields, `disable-model-invocation` |
| Configuration-driven bounds | plan-critique-skills | `workflow.py` counters, `TIER_PHASES` |
| Security controls | none of the three | `policy.py` (hard denials, injection floor, redaction) |
| Independent review | implied by plan-critique | `agents.py` (no self-review, writer serialisation) |
| Persistence | plan-critique's execution-state format | `state.py` (atomic, versioned, append-only log) |
| Multi-platform output | plan-critique's three platform docs | `adapters.py` (five generated trees) |
| Regression protection | prompt-improver's test suite | `evals/` + `tests/` (82 cases, 318 tests) |

The common gap: **none of the three can fail on the behaviour that matters.**
prompt-master and plan-critique are text a model may follow. prompt-improver
tests its engine but not the outcome of a nudge. ZyRompts is built so the parts
that matter can fail loudly, in a suite, before a user notices.
