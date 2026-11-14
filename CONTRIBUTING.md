# Contributing

The project's own principles apply to contributions to it. Two of them decide
most reviews:

1. **If a rule must hold, it is code.** A pull request that adds a rule as prose
   when it could be a check will be asked to add the check.
2. **Evidence or it did not happen.** A change that claims to fix something
   without a test that fails before it and passes after it is not finished.

## Setup

```bash
git clone <your-fork> ZyRompts
cd ZyRompts
python3 -m pip install -e core          # optional; PYTHONPATH=core works too
python3 -m pytest tests/ -q             # the full suite
PYTHONPATH=core python3 -m zyrompts validate
PYTHONPATH=core python3 -m zyrompts eval
```

No third-party runtime dependencies. `pytest` is the only development
dependency.

## Before you open a pull request

- [ ] `python3 -m pytest tests/ -q` passes.
- [ ] `zyrompts validate` passes.
- [ ] `zyrompts eval` passes.
- [ ] `python3 scripts/generate-adapters.py --check` passes, or you ran
      `generate-adapters.py` and committed the output.
- [ ] A test fails without your change and passes with it.
- [ ] `CHANGELOG.md` has an entry under `[Unreleased]`.

## What a good change looks like

**A new hook rule.** One JSON file under `hooks/rules/<Event>/`. Include the
trigger, the injected text, and a priority. Add a case to `evals/datasets/` if
the rule's trigger is subtle. No Python change.

**A new skill.** A directory under `skills/<name>/` with a `SKILL.md` carrying
the five sections the validator enforces: Purpose, Procedure, Failure handling,
Evaluation cases, Version. Activation, Rules, Input/Output and the reference
tables are expected but optional, so `scripts/validate-repo.py` does not fail on
a skill that leaves them out. Declare `depends-on` in the frontmatter. Then run
`generate-adapters.py` so every platform gets it.

**A new policy rule.** A pattern in `policy.py` plus a test in
`tests/test_policy.py` plus an eval case. A hard denial needs a case that
asserts it fires under `yolo`, because that is the case that matters.

**A new platform adapter.** A pure renderer plus a builder plus a `BUILDERS`
entry plus a row in `docs/compatibility-matrix.md`.

## Style

- Python 3.9 compatible. No `match`, no `X | Y` in annotations at runtime
  without `from __future__ import annotations`.
- Standard library only in `core/`.
- Type hints on public functions.
- Comments explain *why*, not *what*. A comment that restates the code is
  deleted in review.
- No em dashes in prose, no emojis. The decorum policy applies to the
  repository too.
- Tests are named for the behaviour they protect, not the function they call.

## Commits

Conventional Commits:

```
feat(classify): raise a wide-scope terse request above LIGHT
fix(policy): deny a bare command under yolo
docs(adr): record the hooks-fail-silent decision
test(review): pin that structural headings are not chapters
```

One logical change per commit. A commit that mixes a fix and a refactor gets
split in review.

**On attribution:** this repository's decorum policy says an agent should not add
a co-author trailer unless the project requires it. If your tooling adds one by
default, that is fine here; if it does not, do not add one by hand. The project
does not require it.

## Review

Every change gets an independent review, and the reviewer is never the author.
Expect findings graded CRITICAL/HIGH/MEDIUM/LOW, each with evidence and a
suggested fix. CRITICAL and HIGH block merge.

Disagree with evidence. "I think it is fine" is not a response to a finding;
"here is the test that shows it is fine" is.
