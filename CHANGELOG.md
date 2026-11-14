# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

**Policy engine: hard denials could be spelled past.** The deny table matched
raw command text, so the same destructive command in a different spelling was
allowed under `yolo`. Each of these was an ALLOW before this change:

- `rm -fr /`, `rm -r -f /`, `rm --recursive --force /` (flag bundling and long
  flags), `RM -RF /` (case), `/bin/rm -rf /` (path-qualified binary),
  `sh -c 'rm -rf /'` (inner shell), `rm -rf /tmp/../` (`..` segments) and
  `rm -rf ${HOME}` (brace expansion).
- `GIT RESET --HARD` and `GIT PUSH --FORCE origin main`: every hard-deny
  pattern is now case-insensitive.
- `bash <(curl …)`, `source <(curl …)` and `eval "$(curl …)"`: remote code
  reaching a shell without a pipe.
- `find / -delete`, `find . -exec rm …` and `grep … | xargs rm -rf`: deletes
  that never use the word `rm`.

**The read-only fast path could be chained past.** `ls; rm -rf /tmp/x` and
`ls $(rm -rf /tmp/x)` were allowed under `read-only` autonomy because the
allowlist matched a prefix. The fast path now requires a single, un-chained
command, and it no longer covers `find` with destructive flags, any pipe or
redirect, or a read of a protected path (`cat /etc/shadow`).

**Protected paths could be spelled past.** `/etc//passwd`, `/etc/./passwd` and
`/etc/../etc/passwd` name the same file as `/etc/passwd` but were allowed. The
path is normalised with `posixpath.normpath` before the check.

**An allow list could bypass a hard denial.** `PolicyConfig(allow_tools={"Bash"},
allow_commands=["*"])` returned ALLOW for `rm -rf /`. Hard denials are now
evaluated before either list and cannot be configured away.

**Redaction missed five credential shapes.** Fine-grained GitHub PATs
(`github_pat_…`), AWS secret access keys, Stripe keys (`sk_live_…`), Google API
keys (`AIza…`) and npm tokens (`npm_…`) passed through verbatim.

**`..` after a home root folded back to a relative path.** The normaliser
substituted a relative sentinel for `~`, so `normpath` collapsed `rm -rf ~/..`
to `.`, which read as an ordinary directory and was allowed under every
autonomy level. The sentinel is absolute now, so `~/..` folds to `/`.

**An allow list lifted the injection floor.** `PolicyConfig` returned ALLOW for
an `allow_tools` or `allow_commands` match before the floor was applied, so a
configuration that trusted a tool also trusted whatever content arrived with
it. Both allow paths now run through the floor.

**The generated Claude Code plugin could not run its own hooks.** `hooks.json`
dispatched to `scripts/engine.py`, which no build target ever wrote, so every
hook in the installed plugin failed with "can't open file". The generator now
emits the dispatcher and a test asserts that the path a manifest names is a
path the same build writes.

**An adapter could write outside its tree.** A skill whose frontmatter named
`../../escape` produced a path outside the target directory. `AdapterResult.write`
resolves every path and refuses one that leaves the root.

**A corrupt state file was destroyed by the next save.** `StateStore.load`
swallowed a parse error and returned an empty state, so the following `save()`
overwrote the only copy. The unreadable file is moved aside once now. A newer
schema still raises, because a readable file the code does not understand is a
different problem.

**The event log wrote credentials to disk verbatim.** `StateStore.log` is where
a session's own words are kept, and a goal or a note routinely quotes a command
or a config line. Every logged value is redacted now, including nested lists and
dicts.

**A malformed eval dataset reported a pass.** An entirely unparsable dataset
loaded zero cases and printed `0/0`, and a dataset whose name matched no
evaluator returned an empty report: both read as success. Load problems are
reported per line, `EvalReport.is_clean()` is false for an empty suite, and
`zyrompts eval` exits 1.

**`Verdict.redacted_args` was declared and never assigned.** A verdict is
printed and often logged, and a tool call routinely carries a token. `evaluate`
now attaches the redacted arguments whenever the call's arguments held a
credential, and omits the field when they did not.

**A typo in `match_target` was silent.** `validate_rule` rejects an unknown
target now, naming the legal ones. At runtime `target_value` still returns `""`
so a rule that slipped through stays inert rather than matching the wrong field.

**The two bypass checks disagreed on `/`.** `handlers._is_bypass` treated a
leading `/` as a slash command; the engine's `_bypassed` did not, so an action
rule without `non_slash` fired on every slash command. The engine matches the
handler now, as the architecture document always claimed.

**The site's count check missed the markup form.** `<b>101</b> eval cases` did
not match, and the agent count was hardcoded. Both are derived now.

**Two CI security steps passed vacuously.** The redaction step was a negative
grep, so a CLI that exited 0 with no output passed it; the dispatcher step
asserted only the exit status, so a dispatcher with no rules loaded also passed.
Both assert on the printed output now.

**The site's link checker ignored CSS `url()`.** A deleted font shipped broken
with no error. Every `url()` in every stylesheet is resolved now.

### Added

- 118 regression tests covering each bypass spelling above, plus the credential
  shapes, so none of them can return silently.
- 58 further tests for the second audit: home-root `..` spellings, the allow-list
  floor, state quarantine and log redaction, the eval harness's failure modes,
  the plugin dispatcher, adapter path containment, slash-prefix parity and
  `match_target` validation.
- 19 policy eval cases (27 -> 46) and 10 redaction tests (9 shapes and one
  false-positive guard).
- `scripts/validate-repo.py` now checks the counts the site quotes (eval cases,
  rules, skills, commands, agent roles) against the repository, so a stale
  figure fails CI instead of shipping. The command and agent counts are derived
  from the code, not written down.
- `ZYROMPTS_ROOT` is documented in the README install section. The rules,
  skills and datasets are read from the repository rather than the installed
  package, so a non-editable install needs it, and every data-reading command
  now prints the same hint when the data is missing.

### Changed

- `pyproject.toml` declares `license = "MIT"` as an SPDX string and drops the
  deprecated license classifier. The build requirement moves to
  `setuptools>=77`, the floor for that form. The old table form is refused from
  2027-02-18.
- `zyrompts validate` explains the `ZYROMPTS_ROOT` fix when it cannot find the
  data, instead of listing missing files with no next step.

## [0.1.0] - 2026-11-13

First release. The framework is complete and tested: a deterministic core, a
declarative hook engine, a canonical skill library, generated platform adapters
and an eval harness.

### Added

**Core engine** (`core/zyrompts/`, dependency-free, Python 3.9+)

- `classify`: intent, complexity, workflow tier, ambiguity findings and
  injection detection, with a no-anchor floor and a wide-scope override.
- `prompts`: 0-100 scoring across seven weighted dimensions, framework choice
  (RTF, CO-STAR, RISEN, CRISPE, few-shot), rewriting with open questions, and
  model-family guidance.
- `policy`: four autonomy levels, a hard-deny table that fires under YOLO,
  protected paths, workspace containment, the untrusted-content injection floor,
  and secret redaction.
- `hooks`: one dispatcher, JSON rule registry, priority merge, validation
  against a capability matrix, and exit-0 on every path.
- `handlers`: named handlers (`intake`, `verify_stop`, `memory_recall`) and
  matchers (`plan_exists`, `has_acceptance_criteria`, `is_high_complexity`),
  reachable only by name from a rule.
- `state`: atomic, schema-versioned project state with an append-only JSONL
  event log.
- `workflow`: 13 phases, per-phase gates, four tiers, bounded critique (3) and
  fix (2) loops, and a block that records where to resume.
- `review`: deterministic plan, specification and diff critique with
  CONFIRMED/UNVERIFIED confidence, a refutation step, and BLOCK/REVISE/PASS.
- `research`: source tiering, evidence-derived confidence, freshness, and gap
  reporting.
- `agents`: 13 role specs, a bounded orchestrator, writer serialisation, and
  structural review independence.
- `adapters`: pure renderers for Claude Code, Gemini, Copilot, Codex and
  OpenCode, plus dependency-graph cycle detection.
- `evals`: JSONL datasets with four evaluators and per-case failure isolation.
- `decorum`: the behaviour policy and a deterministic checker for the five
  mechanical failures.
- `telemetry`: tier-priced cost and duration accounting.
- `cli`: 13 commands, each usable as a gate via its exit code.

**Content**

- 17 canonical skills, each with purpose, activation, procedure, rules, failure
  handling, evaluation cases, version and machine-readable dependencies.
- 6 agent role contracts that mirror `agents.py:REGISTRY`.
- 13 declarative hook rules across five events.
- 6 document templates (specification, plan, critique, task list, execution log,
  acceptance tests).
- 82 eval cases across classification, policy, prompt scoring and injection.
- 318 tests.

**Documentation**

- README, architecture, security model, decorum policy, compatibility matrix,
  and four ADRs.

### Fixed during development

Defects found by writing the tests first:

- `StateStore` constructed over an existing project started empty and the next
  save destroyed the task list.
- A blocked workflow could advance past its gate: `BLOCKED` had no resume point,
  so `advance()` treated it as the end of the chain and jumped to `DONE`.
- The decorum evidence check accepted "all tests pass" as proof of itself.
- Handler-backed rules ignored bypass prefixes that the engine honoured.
- An unknown `match_target` silently matched nothing instead of being reported.
  `validate_rule` now rejects it and names the legal targets.
- `zyrompts policy "rm -rf /" --autonomy yolo` returned **allow**, because
  argparse's default `"{}"` is truthy and the bare-command path never ran.
- `critique_plan` graded structural headings ("Out of scope", "Rollback") as
  chapters, so a correct plan failed its own critique.

[Unreleased]: https://github.com/izynu/ZyRompts/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/izynu/ZyRompts/releases/tag/v0.1.0
