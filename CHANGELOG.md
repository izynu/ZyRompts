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

**Redaction missed six credential shapes.** Fine-grained GitHub PATs
(`github_pat_…`), AWS secret access keys, Stripe keys (`sk_live_…`), Google API
keys (`AIza…`) and npm tokens (`npm_…`) passed through verbatim.

### Added

- 118 regression tests covering each bypass spelling above, plus the credential
  shapes, so none of them can return silently.
- 19 policy eval cases (27 -> 46) and 10 redaction tests (9 shapes and one
  false-positive guard).
- `scripts/validate-repo.py` now checks the counts the site quotes (eval cases,
  rules, skills, commands, agent roles) against the repository, so a stale
  figure fails CI instead of shipping.
- `ZYROMPTS_ROOT` is documented in the README install section. The rules,
  skills and datasets are read from the repository rather than the installed
  package, so a non-editable install needs it.

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
- `decorum`: the behaviour policy and a deterministic checker for the three
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
- `zyrompts policy "rm -rf /" --autonomy yolo` returned **allow**, because
  argparse's default `"{}"` is truthy and the bare-command path never ran.
- `critique_plan` graded structural headings ("Out of scope", "Rollback") as
  chapters, so a correct plan failed its own critique.

[Unreleased]: https://github.com/<owner>/ZyRompts/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/<owner>/ZyRompts/releases/tag/v0.1.0
