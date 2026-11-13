#!/usr/bin/env python3
"""Generate every platform adapter tree from the canonical skills.

The adapters are build output. Editing `adapters/` by hand is the mistake this
script exists to prevent: the canonical skill is the only source of truth, and
the generated tree must be reproducible from it byte for byte.

    python3 scripts/generate-adapters.py            # write
    python3 scripts/generate-adapters.py --check    # fail if committed tree drifted
    python3 scripts/generate-adapters.py --target gemini,copilot
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "core"))

from zyrompts.adapters import BUILDERS, load_canonical_skills  # noqa: E402

DESCRIPTION = "Modular multi-agent workflow framework for AI coding agents"


def version_of() -> str:
    path = REPO / "VERSION"
    return path.read_text(encoding="utf-8").strip() if path.is_file() else "0.1.0"


def build_all(targets: list[str]) -> dict[str, str]:
    skills = load_canonical_skills(REPO / "skills")
    if not skills:
        raise SystemExit("no canonical skills found under skills/")
    version = version_of()
    files: dict[str, str] = {}
    for target in targets:
        builder = BUILDERS.get(target)
        if builder is None:
            raise SystemExit(f"unknown target {target!r}; choose from {', '.join(BUILDERS)}")
        result = (builder(skills, version, DESCRIPTION) if target == "claude-code"
                  else builder(skills, version))
        files.update(result.files)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if the committed tree differs from a fresh build")
    parser.add_argument("--target", default="", help="comma separated; default all")
    args = parser.parse_args(argv)

    targets = args.target.split(",") if args.target else list(BUILDERS)
    files = build_all(targets)

    if args.check:
        stale = []
        for relative, content in files.items():
            path = REPO / relative
            if not path.is_file():
                stale.append(f"missing  {relative}")
            elif path.read_text(encoding="utf-8") != content:
                stale.append(f"differs  {relative}")
        for path in (REPO / "adapters").rglob("*") if (REPO / "adapters").is_dir() else []:
            if path.is_file():
                relative = str(path.relative_to(REPO))
                if relative not in files:
                    stale.append(f"orphaned {relative}")
        if stale:
            print(f"{len(stale)} adapter file(s) out of date:")
            for line in stale:
                print(f"  {line}")
            print("\nrun: python3 scripts/generate-adapters.py")
            return 1
        print(f"adapters up to date ({len(files)} files)")
        return 0

    for relative, content in files.items():
        path = REPO / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    print(f"wrote {len(files)} files for {', '.join(targets)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
