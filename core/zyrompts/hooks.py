"""Declarative hook engine.

One engine dispatches every hook event. Each capability is a data row in
`hooks/rules/<EventName>/*.json`, not a separate script, so adding a nudge is a
single JSON file with zero Python changes.

Contract (mirrors the Claude Code hook protocol):
- invoked as ``python -m zyrompts.hooks <EventName>``; the JSON payload arrives
  on stdin
- reads stdin once, runs the event's rules, merges ``inject_context`` fragments
  by priority with a blank-line join, prints one ``hookSpecificOutput`` object
- exits 0 on every path: a missing event, an unparsable payload, or a bad rule
  is a clean no-op, never a crash that blocks the user's prompt

Safety properties carried over from the prompt-improver design:
- ``*`` / ``#`` / slash prefixes and harness machine events bypass prompt rules
- a rule whose ``event`` does not match its parent directory is skipped
- handlers and matchers are referenced by string name against allowlists only;
  no eval, no importlib, no getattr-on-path
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# --- capability matrix ------------------------------------------------------
# Only inject_context is implemented. block/permission actions are a future
# type; the engine already knows which events could carry them.
CAPABILITY_MATRIX: dict[str, set[str]] = {
    "UserPromptSubmit": {"inject_context"},
    "PreToolUse": {"inject_context"},
    "SubagentStart": {"inject_context"},
    "SessionStart": {"inject_context"},
    "Stop": {"inject_context"},
}

# Where each criteria.match_target reads its value from. A tuple is a nested
# path walked dict-by-dict; a string is a top-level key.
_TARGET_KEYS: dict[str, str | tuple[str, ...]] = {
    "prompt": "prompt",
    "tool_name": "tool_name",
    "agent_type": "agent_type",
    "command": ("tool_input", "command"),
    "file_path": ("tool_input", "file_path"),
    "source": "source",
    "transcript": "transcript_path",
}

_FLAG_MAP = {
    "ignorecase": re.IGNORECASE,
    "multiline": re.MULTILINE,
    "dotall": re.DOTALL,
}

MACHINE_EVENT_PREFIXES = (
    "<task-notification>",
    "<command-name>",
    "<command-message>",
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<local-command-caveat>",
    "<system-reminder>",
)


def is_machine_event(text: str) -> bool:
    """True if text starts (after leading whitespace) with a harness tag."""
    return text.lstrip().startswith(MACHINE_EVENT_PREFIXES)


def default_rules_dir() -> Path:
    """Resolve the bundled rules directory.

    Order: $ZYROMPTS_RULES_DIR, then the package's sibling ``hooks/rules``
    (repo layout), then ``~/.zyrompts/hooks/rules`` (installed layout).
    """
    env = os.environ.get("ZYROMPTS_RULES_DIR")
    if env:
        return Path(env).expanduser()
    package_root = Path(__file__).resolve().parent.parent.parent
    candidate = package_root / "hooks" / "rules"
    if candidate.is_dir():
        return candidate
    return Path.home() / ".zyrompts" / "hooks" / "rules"


# --- rule model -------------------------------------------------------------

@dataclass
class Rule:
    id: str
    event: str
    action: dict | None = None
    handler: str | None = None
    criteria: dict | None = None
    bypass: str = "default"
    priority: int = 100
    description: str = ""

    @classmethod
    def from_dict(cls, row: dict) -> "Rule":
        return cls(
            id=row.get("id", ""),
            event=row.get("event", ""),
            action=row.get("action"),
            handler=row.get("handler"),
            criteria=row.get("criteria"),
            bypass=row.get("bypass", "default"),
            priority=int(row.get("priority", 100)),
            description=row.get("description", ""),
        )


@dataclass
class RuleSet:
    rules: list[Rule] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _compile_flags(flags) -> int:
    result = 0
    for name in flags or []:
        result |= _FLAG_MAP.get(name, 0)
    return result


def validate_rule(row: dict, seen_ids: set[str] | None = None) -> list[str]:
    """Return validation errors for a raw rule row (empty means valid)."""
    from . import handlers as handler_module

    errors: list[str] = []
    seen_ids = seen_ids or set()

    rule_id = row.get("id")
    if not rule_id or not isinstance(rule_id, str):
        errors.append("missing or non-string 'id'")
    elif rule_id in seen_ids:
        errors.append(f"duplicate id {rule_id!r}")

    event = row.get("event")
    if not event:
        errors.append("missing 'event'")
    elif event not in CAPABILITY_MATRIX:
        errors.append(f"unknown event {event!r}")

    has_action = "action" in row
    has_handler = "handler" in row
    if has_action and has_handler:
        errors.append("rule has both 'action' and 'handler' (exactly one allowed)")
    elif not has_action and not has_handler:
        errors.append("rule has neither 'action' nor 'handler'")

    if has_handler and row.get("handler") not in handler_module.HANDLERS:
        errors.append(f"unknown handler {row.get('handler')!r}")

    if has_action:
        action = row.get("action") or {}
        legal = CAPABILITY_MATRIX.get(event, set())
        if action.get("type") not in legal:
            errors.append(f"action type {action.get('type')!r} not legal for event {event!r}")
        for clause in action.get("append_when", []) or []:
            for pattern in clause.get("match", []) or []:
                try:
                    re.compile(pattern)
                except re.error as exc:
                    errors.append(f"append_when regex {pattern!r} does not compile: {exc}")

    criteria = row.get("criteria")
    if criteria:
        flags = _compile_flags(criteria.get("flags"))
        for key in ("match", "exclude"):
            for pattern in criteria.get(key, []) or []:
                try:
                    re.compile(pattern, flags)
                except re.error as exc:
                    errors.append(f"{key} regex {pattern!r} does not compile: {exc}")
        builtin = criteria.get("builtin")
        if builtin and builtin not in handler_module.MATCHERS:
            errors.append(f"unknown builtin matcher {builtin!r}")

    return errors


def load_rules(rules_dir: Path | None = None) -> RuleSet:
    """Load and validate every bundled rule.

    A file may hold one rule object or an array of them. The parent directory
    names the event and is authoritative. Invalid rows and unparsable files are
    skipped with a note so one bad row can never suppress the rest.
    """
    directory = Path(rules_dir).expanduser() if rules_dir else default_rules_dir()
    result = RuleSet()
    if not directory.is_dir():
        result.errors.append(f"rules directory not found: {directory}")
        return result

    seen_ids: set[str] = set()
    for path in sorted(directory.glob("**/*.json")):
        dir_event = path.parent.name
        if dir_event == directory.name:
            result.errors.append(f"skipping {path.name}: not in an event subdirectory")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            result.errors.append(f"skipping {path.name}: {exc}")
            continue

        rows = data if isinstance(data, list) else [data]
        for row in rows:
            if not isinstance(row, dict):
                result.errors.append(f"skipping non-object rule in {path.name}")
                continue
            errors = validate_rule(row, seen_ids)
            if row.get("event") != dir_event:
                errors.append(f"event {row.get('event')!r} does not match directory {dir_event!r}")
            if errors:
                result.errors.append(f"skipping rule {row.get('id', '<no id>')}: {'; '.join(errors)}")
                continue
            seen_ids.add(row["id"])
            result.rules.append(Rule.from_dict(row))
    return result


def _as_patterns(values, flags: int = 0) -> list:
    """Compile strings, pass compiled patterns through untouched.

    Idempotence matters because `fragment_for` compiles a rule handed to it by a
    caller, and `run_event` hands it rules that `rules_for` already compiled.
    Re-compiling a `re.Pattern` raises, so the pass-through is load-bearing.
    """
    out = []
    for value in values or []:
        out.append(value if isinstance(value, re.Pattern) else re.compile(value, flags))
    return out


def _compile_rule(rule: Rule) -> Rule:
    compiled = Rule(**vars(rule))
    criteria = dict(compiled.criteria) if compiled.criteria else None
    if criteria:
        flags = _compile_flags(criteria.get("flags"))
        if "match" in criteria:
            criteria["match"] = _as_patterns(criteria["match"], flags)
        if "exclude" in criteria:
            criteria["exclude"] = _as_patterns(criteria["exclude"], flags)
    compiled.criteria = criteria
    action = dict(compiled.action) if compiled.action else None
    if action and "append_when" in action:
        clauses = []
        for clause in action["append_when"]:
            clause = dict(clause)
            if "match" in clause:
                clause["match"] = _as_patterns(clause["match"])
            clauses.append(clause)
        action["append_when"] = clauses
    compiled.action = action
    return compiled


def rules_for(event: str, rules_dir: Path | None = None) -> list[Rule]:
    """Return compiled rules for one event (empty for unknown events)."""
    if event not in CAPABILITY_MATRIX:
        return []
    return [_compile_rule(r) for r in load_rules(rules_dir).rules if r.event == event]


# --- evaluation -------------------------------------------------------------

def target_value(data: dict, match_target: str) -> str:
    # An unknown target must not fall back to the prompt. A typo in a rule would
    # then silently match a different field than the author intended, which is
    # worse than matching nothing: validate_rule rejects the typo, and this
    # returns "" so a rule that slipped through stays inert.
    if match_target not in _TARGET_KEYS:
        return ""
    key = _TARGET_KEYS[match_target]
    if isinstance(key, tuple):
        value: object = data
        for part in key:
            value = value.get(part, "") if isinstance(value, dict) else ""
    else:
        value = data.get(key, "")
    return value if isinstance(value, str) else ""


def _bypassed(value: str, match_target: str, bypass: str) -> bool:
    if bypass == "none" or match_target != "prompt":
        return False
    stripped = value.lstrip()
    return (not stripped or stripped.startswith("*") or stripped.startswith("#")
            or is_machine_event(stripped))


def _passes_criteria(data: dict, criteria: dict) -> bool:
    from . import handlers as handler_module

    match_target = criteria.get("match_target", "prompt")
    value = target_value(data, match_target)

    if criteria.get("non_slash") and value.lstrip().startswith("/"):
        return False

    builtin = criteria.get("builtin")
    if builtin:
        matcher = handler_module.MATCHERS.get(builtin)
        if matcher is None or not matcher(value.lstrip(), data):
            return False

    match = criteria.get("match")
    if match and not any(p.search(value) for p in match):
        return False

    exclude = criteria.get("exclude")
    if exclude and any(p.search(value) for p in exclude):
        return False

    return True


def _render_action(data: dict, action: dict, match_target: str = "prompt") -> str:
    fragment = "\n".join(action.get("text", []) or [])
    value = target_value(data, match_target)
    for clause in action.get("append_when", []) or []:
        if any(p.search(value) for p in clause.get("match", []) or []):
            fragment += " " + " ".join(clause.get("text", []) or [])
    return fragment


def fragment_for(data: dict, rule: Rule) -> str | None:
    """Return this rule's fragment, or None when it does not fire."""
    from . import handlers as handler_module

    if rule.handler:
        handler = handler_module.HANDLERS.get(rule.handler)
        return handler(data) if handler else None

    # Accept an uncompiled rule. `run_event` compiles on load, but a caller
    # building a Rule by hand should not have to know that, and a str pattern
    # would otherwise raise deep inside the match loop.
    rule = _compile_rule(rule)

    criteria = rule.criteria
    match_target = criteria.get("match_target", "prompt") if criteria else "prompt"

    if criteria is not None:
        value = target_value(data, match_target)
        if _bypassed(value, match_target, rule.bypass):
            return None
        if not _passes_criteria(data, criteria):
            return None

    return _render_action(data, rule.action or {}, match_target)


def run_event(event: str, payload: dict, rules_dir: Path | None = None) -> str:
    """Run every rule for an event and return the merged context (or '')."""
    fragments: list[tuple[int, str]] = []
    for rule in rules_for(event, rules_dir):
        try:
            fragment = fragment_for(payload, rule)
        except Exception as exc:  # noqa: BLE001 - one bad rule must not suppress others
            print(f"[zyrompts] rule {rule.id} raised: {exc}", file=sys.stderr)
            continue
        if fragment:
            fragments.append((rule.priority, fragment))
    if not fragments:
        return ""
    fragments.sort(key=lambda pair: pair[0])
    return "\n\n".join(fragment for _, fragment in fragments)


def _read_payload() -> dict:
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    except (OSError, ValueError):
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    event = argv[0] if argv else None
    if not event or event not in CAPABILITY_MATRIX:
        return 0

    rules_dir = default_rules_dir()
    if not any(rules_dir.glob("**/*.json")):
        return 0

    payload = _read_payload()
    merged = run_event(event, payload, rules_dir)
    if not merged:
        return 0

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": merged,
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
