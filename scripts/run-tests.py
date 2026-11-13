#!/usr/bin/env python3
"""Run the full local gate: tests, validate, evals, adapter sync, health.

This is the same sequence CI runs, in the same order, so a green local run and a
green CI run mean the same thing.

    python3 scripts/run-tests.py
    python3 scripts/run-tests.py --quick     # skip the eval suites
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CORE = REPO / "core"


def run(label: str, *args: str) -> bool:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(CORE)
    print(f"\n== {label}")
    print(f"   {' '.join(args)}")
    result = subprocess.run(args, cwd=str(REPO), env=env)
    ok = result.returncode == 0
    print(f"   {'ok' if ok else 'FAILED'}")
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--quick", action="store_true", help="skip the eval suites")
    args = parser.parse_args(argv)

    python = sys.executable
    steps = [
        ("unit and integration tests",
         run("tests", python, "-m", "pytest", "tests/", "-q")),
        ("validate rules, skills, dependency graph",
         run("validate", python, "-m", "zyrompts", "validate")),
    ]
    if not args.quick:
        steps.append(("eval datasets",
                      run("eval", python, "-m", "zyrompts", "eval")))
    steps.extend([
        ("repository contract",
         run("repo", python, str(REPO / "scripts" / "validate-repo.py"))),
        ("adapters in sync",
         run("adapters", python, str(REPO / "scripts" / "generate-adapters.py"), "--check")),
        ("health",
         run("health", python, "-m", "zyrompts", "health")),
    ])

    failed = [label for label, ok in steps if not ok]
    print("\n" + "=" * 60)
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
