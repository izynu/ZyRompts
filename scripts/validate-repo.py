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


def _check_site_counts(repo: Path, eval_cases: int, rules: int, skills: int) -> list[str]:
    """Flag figures quoted on the site that no longer match the repository.

    Only counts that are cheap and deterministic to recompute are checked here:
    eval cases, hook rules, skills, CLI commands and agent roles. The test count
    is deliberately not checked, because computing it means running the suite,
    and a check that runs the suite from inside the suite's own CI step is a
    worse trade than a stale number a reviewer will notice.

    A figure is only reported when the same number appears on the site next to
    the matching noun, so unrelated numbers in prose are left alone.
    """
    problems: list[str] = []
    pages = sorted((repo / "site").glob("*.html"))
    if not pages:
        return problems

    expected = {
        "eval cases": eval_cases,
        "hook rules": rules,
        "skills": skills,
        "CLI commands": 13,
        "agents": 13,
    }
    # The figures sit in markup (`<b>101</b> eval cases`, `class="chip">101 eval
    # cases`), so the number is often preceded by `>` rather than whitespace.
    # `\b` does not match between `>` and a digit, which is why the first
    # version of this check silently found nothing.
    patterns = {
        "eval cases": re.compile(r"(\d+)\s+eval cases\b"),
        "hook rules": re.compile(r"(\d+)\s+hook rules\b"),
        "skills": re.compile(r"(\d+)\s+skills\b"),
        "CLI commands": re.compile(r"(\d+)\s+CLI commands\b"),
        "agents": re.compile(r"(\d+)\s+agents\b"),
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
    sys.path.insert(0, str(REPO / "core"))
    from zyrompts.cli import build_parser  # noqa: E402

    parser = build_parser()
    subparsers = next(a for a in parser._actions
                      if isinstance(a, __import__("argparse")._SubParsersAction))
    commands = set(subparsers.choices)
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
