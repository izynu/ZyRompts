"""Command line interface.

Every capability has a command so it can be used, tested and scripted without
a model in the loop. `zyrompts` with no arguments prints the health summary.

Commands:
    classify <prompt>      classify a prompt and show the signals
    score <prompt>         score a prompt 0-100 with the missing dimensions
    improve <prompt>       rewrite a prompt into a structured framework
    policy <tool> <json>   evaluate a tool call against the policy engine
    plan-critique <file>   run deterministic plan critique
    diff-review <file>     run deterministic diff review
    adapters [--write]     generate platform adapter trees
    validate               validate rules, skills and manifests
    eval                   run the eval datasets
    health                 environment and installation check
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .adapters import BUILDERS, dependency_cycles, load_canonical_skills
from .classify import classify
from .decorum import DECORUM_VERSION, DECORUM, check_reply
from .evals import run_all
from .hooks import CAPABILITY_MATRIX, load_rules
from .policy import KNOWN_TOOLS, Autonomy, evaluate, redact_secrets
from .prompts import improve_prompt, model_notes, score_prompt
from .review import critique_diff, critique_plan


def repo_root() -> Path:
    env = os.environ.get("ZYROMPTS_ROOT")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parent.parent.parent


def _print(data) -> None:
    if isinstance(data, str):
        print(data)
    else:
        print(json.dumps(data, indent=2))


def cmd_classify(args) -> int:
    result = classify(args.prompt)
    _print(result.to_dict())
    return 0


def cmd_score(args) -> int:
    breakdown = score_prompt(args.prompt)
    _print(breakdown.to_dict())
    return 0 if breakdown.grade in ("A", "B", "C") else 1


def cmd_improve(args) -> int:
    improved = improve_prompt(args.prompt)
    if args.json:
        _print(improved.to_dict())
    else:
        print(improved.improved)
        print(f"\n--- score {improved.before.total} -> {improved.after.total} "
              f"(+{improved.delta}), framework {improved.framework.value} ---")
        if improved.open_questions:
            print("Open questions:")
            for question in improved.open_questions:
                print(f"  - {question}")
    return 0


def cmd_policy(args) -> int:
    try:
        payload = json.loads(args.args_json) if args.args_json else {}
    except json.JSONDecodeError as exc:
        print(f"invalid JSON args: {exc}", file=sys.stderr)
        return 2

    tool = args.tool
    # `zyrompts policy "rm -rf /"` is the natural way to ask, so a first argument
    # that is not a known tool name and carries no JSON args is read as a shell
    # command. Explicit, not a fallback: known tool names win, and the help text
    # states the rule.
    #
    # The check is `not payload`, not `not args.args_json`: argparse defaults
    # args_json to the string "{}", which is truthy, so testing the raw string
    # meant this never fired and `policy "rm -rf /"` was evaluated as an unknown
    # tool name and allowed under yolo.
    looks_like_command = tool not in KNOWN_TOOLS and not payload
    if looks_like_command:
        payload = {"command": tool}
        tool = "Bash"

    verdict = evaluate(tool, payload, Autonomy(args.autonomy))
    _print(verdict.to_dict())
    return 0 if verdict.decision.value != "deny" else 1


def cmd_plan_critique(args) -> int:
    path = Path(args.file)
    if not path.is_file():
        print(f"no such file: {path}", file=sys.stderr)
        return 2
    existing = None
    if args.check_paths:
        existing = {str(p.relative_to(Path.cwd())) for p in Path.cwd().rglob("*") if p.is_file()}
    report = critique_plan(path.read_text(encoding="utf-8"), existing)
    print(report.to_markdown())
    return 0 if report.verdict() == "PASS" else 1


def cmd_diff_review(args) -> int:
    path = Path(args.file)
    if not path.is_file():
        print(f"no such file: {path}", file=sys.stderr)
        return 2
    report = critique_diff(path.read_text(encoding="utf-8"))
    print(report.to_markdown())
    return 0 if report.verdict() == "PASS" else 1


def cmd_adapters(args) -> int:
    root = repo_root()
    skills = load_canonical_skills(root / "skills")
    if not skills:
        print("no canonical skills found", file=sys.stderr)
        return 2
    version = (root / "VERSION").read_text(encoding="utf-8").strip() if (root / "VERSION").is_file() else __version__
    description = "Modular multi-agent workflow framework for AI coding agents"
    targets = args.targets.split(",") if args.targets else list(BUILDERS)
    total = 0
    for target in targets:
        builder = BUILDERS.get(target)
        if builder is None:
            print(f"unknown adapter target {target!r}", file=sys.stderr)
            continue
        result = builder(skills, version, description) if target == "claude-code" else builder(skills, version)
        if args.write:
            written = result.write(root)
            total += len(written)
            print(f"{target}: wrote {len(written)} files")
        else:
            total += len(result.files)
            print(f"{target}: {len(result.files)} files (dry run)")
    return 0


def cmd_validate(args) -> int:
    root = repo_root()
    problems: list[str] = []

    rule_set = load_rules(root / "hooks" / "rules")
    problems.extend(rule_set.errors)
    if not rule_set.rules:
        problems.append("no hook rules loaded")

    skills = load_canonical_skills(root / "skills")
    known = {skill.name for skill in skills}
    for skill in skills:
        path = root / "skills" / skill.name / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            problems.append(f"{path.relative_to(root)}: missing frontmatter")
        elif "description:" not in text.split("---")[1]:
            problems.append(f"{path.relative_to(root)}: missing description")
        for dep in skill.depends_on + skill.optional_deps:
            if dep not in known:
                problems.append(f"{skill.name}: depends on unknown skill {dep!r}")

    for cycle in dependency_cycles(skills):
        problems.append("dependency cycle: " + " -> ".join(cycle))

    for required in ("README.md", "LICENSE", "VERSION"):
        if not (root / required).is_file():
            problems.append(f"missing {required}")

    if problems:
        print(f"{len(problems)} problem(s) in {root}:")
        for problem in problems:
            print(f"  - {problem}")
        # The data files (rules, skills, datasets) live in the repository, not
        # in the wheel, so a non-editable install resolves `repo_root()` to a
        # path with no data in it. Say which knob fixes that instead of leaving
        # the reader with a list of missing files and no next step.
        if not (root / "hooks" / "rules").is_dir():
            print("\nThis looks like an installed package rather than a clone. "
                  "The rules, skills and datasets are read from the repository, "
                  "so point ZYROMPTS_ROOT at a checkout:\n"
                  "  export ZYROMPTS_ROOT=/path/to/ZyRompts")
        return 1
    print(f"ok: {len(rule_set.rules)} rules, {len(skills)} skills")
    return 0


def cmd_eval(args) -> int:
    root = repo_root()
    reports = run_all(root / "evals" / "datasets")
    if not reports:
        print("no datasets found", file=sys.stderr)
        return 2
    failed = 0
    for report in reports:
        print(f"{report.suite}: {report.passed}/{report.total} ({report.pass_rate:.0%})")
        for failure in report.failures():
            print(f"  FAIL {failure.case_id}: {'; '.join(failure.notes)}")
        failed += len(report.failures())
    return 0 if failed == 0 else 1


def cmd_health(args) -> int:
    root = repo_root()
    rule_set = load_rules(root / "hooks" / "rules")
    skills = list((root / "skills").glob("*/SKILL.md"))
    datasets = list((root / "evals" / "datasets").glob("*.jsonl"))
    info = {
        "version": __version__,
        "root": str(root),
        "python": sys.version.split()[0],
        "rules": len(rule_set.rules),
        "rule_errors": len(rule_set.errors),
        "skills": len(skills),
        "datasets": len(datasets),
        "events": sorted(CAPABILITY_MATRIX),
        "decorum_version": DECORUM_VERSION,
        "healthy": bool(rule_set.rules and skills and not rule_set.errors),
    }
    _print(info)
    return 0 if info["healthy"] else 1


def cmd_decorum(args) -> int:
    if args.check:
        problems = check_reply(args.check)
        if problems:
            for problem in problems:
                print(f"- {problem}")
            return 1
        print("no decorum problems detected")
        return 0
    print(DECORUM)
    return 0


def cmd_models(args) -> int:
    _print({"family": args.family, "guidance": model_notes(args.family)})
    return 0


def cmd_redact(args) -> int:
    # `zyrompts redact "text"` and `zyrompts redact < file` are both natural,
    # so a missing positional reads stdin. Without this the documented pipe form
    # fails with an argparse error and an empty stdout, which looks like a
    # successful redaction of an empty input.
    text = args.text
    if text is None:
        if sys.stdin is None or sys.stdin.isatty():
            print("redact: provide text as an argument or on stdin", file=sys.stderr)
            return 2
        text = sys.stdin.read()
    redacted, kinds = redact_secrets(text)
    _print({"text": redacted, "kinds": kinds})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zyrompts", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"zyrompts {__version__}")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("classify", help="classify a prompt")
    p.add_argument("prompt")
    p.set_defaults(func=cmd_classify)

    p = sub.add_parser("score", help="score a prompt 0-100")
    p.add_argument("prompt")
    p.set_defaults(func=cmd_score)

    p = sub.add_parser("improve", help="rewrite a prompt")
    p.add_argument("prompt")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_improve)

    p = sub.add_parser("policy", help="evaluate a tool call")
    p.add_argument("tool")
    p.add_argument("args_json", nargs="?", default="{}")
    p.add_argument("--autonomy", default="ask",
                   choices=[a.value for a in Autonomy])
    p.set_defaults(func=cmd_policy)

    p = sub.add_parser("plan-critique", help="deterministic plan critique")
    p.add_argument("file")
    p.add_argument("--check-paths", action="store_true")
    p.set_defaults(func=cmd_plan_critique)

    p = sub.add_parser("diff-review", help="deterministic diff review")
    p.add_argument("file")
    p.set_defaults(func=cmd_diff_review)

    p = sub.add_parser("adapters", help="generate platform adapters")
    p.add_argument("--write", action="store_true")
    p.add_argument("--targets", default="")
    p.set_defaults(func=cmd_adapters)

    p = sub.add_parser("validate", help="validate rules, skills, manifests")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("eval", help="run eval datasets")
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("health", help="environment check")
    p.set_defaults(func=cmd_health)

    p = sub.add_parser("decorum", help="print or check the decorum policy")
    p.add_argument("--check", default="")
    p.set_defaults(func=cmd_decorum)

    p = sub.add_parser("models", help="model-specific prompting guidance")
    p.add_argument("family", nargs="?", default="unknown")
    p.set_defaults(func=cmd_models)

    p = sub.add_parser("redact", help="strip credentials from text")
    p.add_argument("text", nargs="?", default=None,
                   help="text to redact; omit to read stdin")
    p.set_defaults(func=cmd_redact)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        return cmd_health(args)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
