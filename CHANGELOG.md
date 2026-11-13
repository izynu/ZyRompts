# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-13

First release. The framework is complete and tested: a deterministic core, a
declarative hook engine, a canonical skill library, generated platform adapters
and an eval harness.

### Added

**Core engine** (`core/zyrompts/`, dependency-free, Python 3.9+)

- `classify` — intent, complexity, workflow tier, ambiguity findings and
  injection detection, with a no-anchor floor and a wide-scope override.
- `prompts` — 0-100 scoring across seven weighted dimensions, framework choice
  (RTF, CO-STAR, RISEN, CRISPE, few-shot), rewriting with open questions, and
  model-family guidance.
- `policy` — four autonomy levels, a hard-deny table that fires under YOLO,
  protected paths, workspace containment, the untrusted-content injection floor,
  and secret redaction.
- `hooks` — one dispatcher, JSON rule registry, priority merge, validation
  against a capability matrix, and exit-0 on every path.
- `handlers` — named handlers (`intake`, `verify_stop`, `memory_recall`) and
  matchers (`plan_exists`, `has_acceptance_criteria`, `is_high_complexity`),
  reachable only by name from a rule.
- `state` — atomic, schema-versioned project state with an append-only JSONL
  event log.
- `workflow` — 13 phases, per-phase gates, four tiers, bounded critique (3) and
  fix (2) loops, and a block that records where to resume.
- `review` — deterministic plan, specification and diff critique with
  CONFIRMED/UNVERIFIED confidence, a refutation step, and BLOCK/REVISE/PASS.
- `research` — source tiering, evidence-derived confidence, freshness, and gap
  reporting.
- `agents` — 13 role specs, a bounded orchestrator, writer serialisation, and
  structural review independence.
- `adapters` — pure renderers for Claude Code, Gemini, Copilot, Codex and
  OpenCode, plus dependency-graph cycle detection.
- `evals` — JSONL datasets with four evaluators and per-case failure isolation.
- `decorum` — the behaviour policy and a deterministic checker for the three
  mechanical failures.
- `telemetry` — tier-priced cost and duration accounting.
- `cli` — 13 commands, each usable as a gate via its exit code.

**Content**

- 17 canonical skills, each with purpose, activation, procedure, rules, failure
  handling, evaluation cases, version and machine-readable dependencies.
- 6 agent role contracts that mirror `agents.py:REGISTRY`.
- 13 declarative hook rules across five events.
- 6 document templates (specification, plan, critique, task list, execution log,
  acceptance tests).
- 82 eval cases across classification, policy, prompt scoring and injection.
- 317 tests.

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
