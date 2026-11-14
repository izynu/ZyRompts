#!/usr/bin/env python3
"""Check the repository against its own contract.

`zyrompts validate` checks the machine-readable parts: rules load, skills parse,
dependencies resolve and form no cycle. This script checks the parts a parser
cannot see: every skill has the sections the contract requires, every rule has a
test, every dataset has cases, and no documented command has drifted from the
CLI.

    python3 scripts/validate-repo.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "core"))

from zyrompts.adapters import load_canonical_skills  # noqa: E402
from zyrompts.hooks import CAPABILITY_MATRIX, load_rules  # noqa: E402

# Sections every skill must carry. Purpose/Procedure/Failure handling are the
# three that stop a skill being a vibe; Version and Evaluation cases are what
# make it maintainable.
REQUIRED_SKILL_SECTIONS = (
    "## Purpose",
    "## Procedure",
    "## Failure handling",
    "## Evaluation cases",
    "## Version",
)


def _cli_commands(repo: Path) -> set[str]:
    """The subcommand names the parser actually exposes.

    Derived, not written down: a hardcoded figure in this file is the same class
    of staleness the check exists to catch.
    """
    import argparse

    from zyrompts.cli import build_parser  # noqa: E402

    parser = build_parser()
    subparsers = next(a for a in parser._actions
                      if isinstance(a, argparse._SubParsersAction))
    return set(subparsers.choices)


def _agent_roles(repo: Path) -> dict:
    from zyrompts.agents import REGISTRY  # noqa: E402

    return REGISTRY


def _adapter_file_count(repo: Path) -> int:
    """Files in the committed adapter tree.

    Counting the committed tree is the same number as the generator produces
    only because CI runs `generate-adapters.py --check` first; that check is
    what makes this figure meaningful rather than a second copy of the drift.
    """
    tree = repo / "adapters"
    if not tree.is_dir():
        return 0
    return sum(1 for path in tree.rglob("*") if path.is_file())


def _collected_test_count(repo: Path) -> int | None:
    """How many test cases pytest would collect, or None if pytest is absent.

    Collection is not execution: nothing in the suite runs, so this is cheap
    (well under a second) and safe to call from a check that itself runs inside
    CI. It counts parametrised expansions, which is why it matches the number
    pytest prints after a real run rather than the number of `def test_` lines.

    Returns None rather than raising when pytest is not installed, so the
    repository check still works from a bare checkout; the caller reports the
    figure as unchecked in that case instead of silently skipping it.
    """
    import subprocess

    try:
        import pytest  # noqa: F401
    except ImportError:
        return None

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q",
         "-p", "no:cacheprovider"],
        cwd=repo, capture_output=True, text=True, timeout=300,
    )
    match = re.search(r"^(\d+) tests? collected", proc.stdout, re.M)
    return int(match.group(1)) if match else None


def _check_site_counts(repo: Path, eval_cases: int, rules: int, skills: int) -> list[str]:
    """Flag figures quoted on the site that no longer match the repository.

    Every count the site quotes is recomputed here from the repository: eval
    cases, hook rules, skills, CLI commands, agent roles, generated adapter files
    and the collected test count. The test figure used to be the exception, on
    the argument that recomputing it meant running the suite; collection answers
    that without running anything, and the figure had already drifted from 436
    to 498 before anyone noticed.

    A figure is only reported when the same number appears on the site next to
    the matching noun, so unrelated numbers in prose are left alone. `files` is
    the loosest of the nouns: the site uses it only for the adapter tree today,
    so a future "3 files changed" in prose would be flagged. That is the safe
    direction for this check.
    """
    problems: list[str] = []
    pages = sorted((repo / "site").glob("*.html"))
    if not pages:
        return problems

    tests = _collected_test_count(repo)
    expected = {
        "eval cases": eval_cases,
        "hook rules": rules,
        "skills": skills,
        "CLI commands": len(_cli_commands(repo)),
        "agents": len(_agent_roles(repo)),
        "files": _adapter_file_count(repo),
    }
    if tests is not None:
        expected["tests"] = tests
    # The figures sit in markup (`<b>101</b> eval cases`, `class="chip">101 eval
    # cases`, `<span><b>101</b> eval cases</span>`), so the number is often
    # separated from the noun by a closing tag or two. `\b` does not match
    # between `>` and a digit, and a plain `\s+` misses the tags, which is why
    # the first two versions of this check silently found nothing. The optional
    # tag group is what makes the `<b>` form match.
    gap = r"\s*(?:</?[a-z][a-z0-9]*[^>]*>\s*)*"
    patterns = {
        "eval cases": re.compile(r"(\d+)" + gap + r"eval cases\b"),
        "hook rules": re.compile(r"(\d+)" + gap + r"hook rules\b"),
        "skills": re.compile(r"(\d+)" + gap + r"skills\b"),
        "CLI commands": re.compile(r"(\d+)" + gap + r"CLI commands\b"),
        "agents": re.compile(r"(\d+)" + gap + r"agents\b"),
        "files": re.compile(r"(\d+)" + gap + r"files\b"),
        "tests": re.compile(r"(\d+)" + gap + r"tests\b"),
    }

    for page in pages:
        text = page.read_text(encoding="utf-8")
        for noun, pattern in patterns.items():
            for match in pattern.finditer(text):
                quoted = int(match.group(1))
                if quoted != expected[noun]:
                    line = text[:match.start()].count("\n") + 1
                    problems.append(
                        f"{page.relative_to(repo)}:{line}: says {quoted} {noun}, "
                        f"repository has {expected[noun]}")
    return problems


def main() -> int:
    problems: list[str] = []

    # --- skills -------------------------------------------------------------
    skills = load_canonical_skills(REPO / "skills")
    if len(skills) < 17:
        problems.append(f"expected at least 17 skills, found {len(skills)}")
    for skill in skills:
        path = REPO / "skills" / skill.name / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        for section in REQUIRED_SKILL_SECTIONS:
            if section not in text:
                problems.append(f"{skill.name}: missing '{section}'")
        if not skill.description:
            problems.append(f"{skill.name}: empty description")
        if len(skill.description) > 300:
            problems.append(f"{skill.name}: description over 300 chars "
                            f"({len(skill.description)})")

    # --- hook rules ---------------------------------------------------------
    rule_set = load_rules(REPO / "hooks" / "rules")
    problems.extend(rule_set.errors)
    covered = {rule.event for rule in rule_set.rules}
    for event in CAPABILITY_MATRIX:
        if event not in covered:
            problems.append(f"no rule covers event {event!r}")

    seen_ids: dict[str, str] = {}
    for rule in rule_set.rules:
        if rule.id in seen_ids:
            problems.append(f"duplicate rule id {rule.id!r}")
        seen_ids[rule.id] = rule.event

    # --- datasets -----------------------------------------------------------
    datasets = sorted((REPO / "evals" / "datasets").glob("*.jsonl"))
    if len(datasets) < 4:
        problems.append(f"expected 4 eval datasets, found {len(datasets)}")
    total_cases = 0
    for path in datasets:
        cases = 0
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                case = json.loads(line)
            except ValueError as exc:
                problems.append(f"{path.name}:{number}: invalid JSON ({exc})")
                continue
            cases += 1
            if not isinstance(case, dict) or "id" not in case:
                problems.append(f"{path.name}:{number}: case has no id")
        if cases == 0:
            problems.append(f"{path.name}: no cases")
        total_cases += cases
    if total_cases < 80:
        problems.append(f"expected at least 80 eval cases, found {total_cases}")

    # --- documented commands ------------------------------------------------
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    commands = _cli_commands(REPO)
    documented = set(re.findall(r"^zyrompts\s+([a-z-]+)", readme, re.M))
    for command in documented - commands:
        problems.append(f"README documents 'zyrompts {command}', which does not exist")
    for command in commands - documented:
        problems.append(f"CLI command '{command}' is not documented in README")

    # --- templates ----------------------------------------------------------
    for template in ("specification.md", "plan.md", "critique.md",
                     "task-list.md", "execution-log.md", "acceptance-tests.md"):
        if not (REPO / "templates" / template).is_file():
            problems.append(f"missing template {template}")

    # --- adapters -----------------------------------------------------------
    if not (REPO / "adapters").is_dir() or not any((REPO / "adapters").iterdir()):
        problems.append("adapters/ is empty; run scripts/generate-adapters.py")

    # --- numbers quoted on the site ----------------------------------------
    #
    # The site states counts (eval cases, tests, rules, skills). Nothing
    # recomputed them, so they silently went stale the moment a case was added.
    # Rather than pin the exact figures here, check that each figure the site
    # quotes is one the repository can still produce, so a wrong number is a
    # failing check instead of a wrong claim.
    problems.extend(_check_site_counts(REPO, total_cases, len(rule_set.rules), len(skills)))

    if problems:
        print(f"{len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"ok: {len(skills)} skills, {len(rule_set.rules)} rules, "
          f"{total_cases} eval cases, {len(commands)} commands")
    return 0


if __name__ == "__main__":
    sys.exit(main())
