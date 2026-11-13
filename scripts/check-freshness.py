#!/usr/bin/env python3
"""Report repository facts that are easy to get wrong and cheap to check.

    python3 scripts/check-freshness.py

Reports, without failing the build unless asked:

- the canonical source, the generated trees, and whether they agree
- the age of the content in each skill (from its Version line and git history
  when available)
- which skills declare dependencies and which are depended upon
- how many eval cases cover each module

The point is a maintenance view, not a gate: `--strict` makes it one.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "core"))

from zyrompts.adapters import BUILDERS, load_canonical_skills  # noqa: E402

# Must match scripts/generate-adapters.py, or the claude-code manifest is
# reported as changed every time. One constant, two callers.
DESCRIPTION = "Modular multi-agent workflow framework for AI coding agents"


def git_age(path: Path) -> str:
    """Last commit date for a path, or a dash when not in git."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ad", "--date=short", "--", str(path)],
            cwd=str(REPO), capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return "-"
    value = out.stdout.strip()
    if not value:
        return "-"
    try:
        days = (date.today() - datetime.strptime(value, "%Y-%m-%d").date()).days
    except ValueError:
        return value
    return f"{value} ({days}d)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 if adapters are stale")
    args = parser.parse_args(argv)

    skills = load_canonical_skills(REPO / "skills")
    version = (REPO / "VERSION").read_text(encoding="utf-8").strip()

    print(f"ZyRompts {version} - {len(skills)} canonical skills\n")

    print("Adapters")
    version_str = version
    stale = 0
    for target, builder in BUILDERS.items():
        result = (builder(skills, version_str, DESCRIPTION) if target == "claude-code"
                  else builder(skills, version_str))
        missing = [p for p in result.files if not (REPO / p).is_file()]
        changed = [p for p, c in result.files.items()
                   if (REPO / p).is_file()
                   and (REPO / p).read_text(encoding="utf-8") != c]
        state = "current" if not missing and not changed else \
            f"{len(missing)} missing, {len(changed)} changed"
        stale += len(missing) + len(changed)
        print(f"  {target:<12} {len(result.files):>3} files  {state}")

    print("\nSkills")
    dependents: Counter[str] = Counter()
    for skill in skills:
        for dep in skill.depends_on:
            dependents[dep] += 1
    for skill in skills:
        deps = ", ".join(skill.depends_on) or "-"
        used = dependents.get(skill.name, 0)
        print(f"  {skill.name:<20} deps: {deps:<22} used by {used:<2} "
              f"last: {git_age(REPO / 'skills' / skill.name)}")

    print("\nEval coverage")
    for path in sorted((REPO / "evals" / "datasets").glob("*.jsonl")):
        cases = sum(1 for line in path.read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.strip().startswith("#"))
        print(f"  {path.stem:<16} {cases:>3} cases")

    print("\nHooks")
    for event_dir in sorted((REPO / "hooks" / "rules").iterdir()):
        if event_dir.is_dir():
            count = len(list(event_dir.glob("*.json")))
            print(f"  {event_dir.name:<18} {count} rule(s)")

    if args.strict and stale:
        print(f"\n{stale} adapter file(s) out of date; run scripts/generate-adapters.py")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
