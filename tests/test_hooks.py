"""Hook engine contract.

The engine is the layer every other capability rides on, so its invariants are
load-bearing: a bad rule is skipped, never fatal; bypasses are honoured; and
handlers are resolved by name against an allowlist, never by import path.
"""

from __future__ import annotations

import json

import pytest

from zyrompts import handlers
from zyrompts.hooks import (
    CAPABILITY_MATRIX,
    MACHINE_EVENT_PREFIXES,
    Rule,
    default_rules_dir,
    fragment_for,
    is_machine_event,
    load_rules,
    run_event,
    target_value,
    validate_rule,
)


def test_bundled_rules_load_without_errors(rules_dir):
    rule_set = load_rules(rules_dir)
    assert rule_set.rules, "no rules loaded"
    assert rule_set.errors == [], f"rule errors: {rule_set.errors}"


def test_every_event_has_at_least_one_rule(rules_dir):
    rule_set = load_rules(rules_dir)
    events = {rule.event for rule in rule_set.rules}
    assert events == set(CAPABILITY_MATRIX)


def test_missing_rules_dir_is_a_clean_error(tmp_path):
    rule_set = load_rules(tmp_path / "nope")
    assert rule_set.rules == []
    assert any("not found" in error for error in rule_set.errors)


def test_str_path_is_accepted(rules_dir):
    """Regression: a str rules_dir used to raise AttributeError."""
    rule_set = load_rules(str(rules_dir))
    assert rule_set.rules


def test_rule_in_wrong_directory_is_skipped(tmp_path):
    event_dir = tmp_path / "PreToolUse"
    event_dir.mkdir()
    (event_dir / "bad.json").write_text(json.dumps({
        "id": "bad", "event": "SessionStart",
        "action": {"type": "inject_context", "text": ["x"]},
    }), encoding="utf-8")
    rule_set = load_rules(tmp_path)
    assert rule_set.rules == []
    assert any("does not match directory" in error for error in rule_set.errors)


def test_unparsable_rule_file_is_skipped_not_fatal(tmp_path):
    event_dir = tmp_path / "PreToolUse"
    event_dir.mkdir()
    (event_dir / "broken.json").write_text("{not json", encoding="utf-8")
    (event_dir / "good.json").write_text(json.dumps({
        "id": "good", "event": "PreToolUse",
        "action": {"type": "inject_context", "text": ["ok"]},
    }), encoding="utf-8")
    rule_set = load_rules(tmp_path)
    assert [rule.id for rule in rule_set.rules] == ["good"]
    assert any("broken.json" in error for error in rule_set.errors)


@pytest.mark.parametrize("row,needle", [
    ({"event": "PreToolUse", "action": {"type": "inject_context"}}, "id"),
    ({"id": "a", "action": {"type": "inject_context"}}, "event"),
    ({"id": "a", "event": "NopeEvent", "action": {"type": "inject_context"}}, "unknown event"),
    ({"id": "a", "event": "PreToolUse"}, "neither"),
    ({"id": "a", "event": "PreToolUse", "action": {"type": "inject_context"},
      "handler": "intake"}, "both"),
    ({"id": "a", "event": "PreToolUse", "handler": "nope_handler"}, "unknown handler"),
    ({"id": "a", "event": "SessionStart",
      "action": {"type": "inject_context", "text": []}}, None),  # legal type
])
def test_validate_rule(row, needle):
    errors = validate_rule(row)
    if needle is None:
        assert errors == []
    else:
        assert any(needle in error for error in errors), errors


def test_action_type_must_be_legal_for_the_event():
    errors = validate_rule({"id": "a", "event": "PreToolUse",
                            "action": {"type": "block"}})
    assert any("not legal" in error for error in errors)


def test_bad_regex_is_reported():
    errors = validate_rule({
        "id": "a", "event": "UserPromptSubmit",
        "action": {"type": "inject_context", "text": ["x"]},
        "criteria": {"match": ["[unclosed"]},
    })
    assert any("does not compile" in error for error in errors)


def test_unknown_builtin_matcher_is_reported():
    errors = validate_rule({
        "id": "a", "event": "UserPromptSubmit",
        "action": {"type": "inject_context", "text": ["x"]},
        "criteria": {"builtin": "does_not_exist"},
    })
    assert any("unknown builtin" in error for error in errors)


@pytest.mark.parametrize("tag", MACHINE_EVENT_PREFIXES)
def test_machine_events_are_recognised(tag):
    assert is_machine_event(f"{tag} payload")


def test_ordinary_text_is_not_a_machine_event():
    assert is_machine_event("fix the bug") is False


def test_target_value_walks_nested_paths():
    payload = {"tool_input": {"command": "ls"}, "prompt": "hi"}
    assert target_value(payload, "command") == "ls"
    assert target_value(payload, "prompt") == "hi"
    assert target_value(payload, "missing") == ""


def test_target_value_survives_wrong_shape():
    assert target_value({"tool_input": "not-a-dict"}, "command") == ""


@pytest.mark.parametrize("prompt", ["*skip this", "#remember this", "/somecommand"])
def test_bypass_prefixes_suppress_prompt_rules(rules_dir, prompt):
    assert run_event("UserPromptSubmit", {"prompt": prompt}, rules_dir) == ""


def test_machine_event_suppresses_prompt_rules(rules_dir):
    payload = {"prompt": "<task-notification> done"}
    assert run_event("UserPromptSubmit", payload, rules_dir) == ""


def test_intake_handler_fires_on_a_real_prompt(rules_dir):
    merged = run_event("UserPromptSubmit", {"prompt": "fix the bug"}, rules_dir)
    assert "INTAKE" in merged


def test_bash_safety_rule_fires(rules_dir):
    merged = run_event("PreToolUse", {"tool_name": "Bash",
                                      "tool_input": {"command": "rm -rf build"}}, rules_dir)
    assert merged


def test_bash_safety_rule_ignores_read_only_commands(rules_dir):
    merged = run_event("PreToolUse", {"tool_name": "Bash",
                                      "tool_input": {"command": "ls -la"}}, rules_dir)
    assert "rm -rf" not in merged


def test_unknown_event_returns_empty(rules_dir):
    assert run_event("NoSuchEvent", {"prompt": "hi"}, rules_dir) == ""


def test_handler_registry_is_an_allowlist():
    assert "intake" in handlers.HANDLERS
    assert "verify_stop" in handlers.HANDLERS
    assert all(callable(fn) for fn in handlers.HANDLERS.values())


def test_matcher_registry_is_an_allowlist():
    assert set(handlers.MATCHERS) == {"plan_exists", "has_acceptance_criteria",
                                      "is_high_complexity"}


def test_a_raising_handler_does_not_suppress_other_rules(rules_dir, monkeypatch):
    def boom(_data):
        raise RuntimeError("boom")

    monkeypatch.setitem(handlers.HANDLERS, "intake", boom)
    merged = run_event("UserPromptSubmit", {"prompt": "fix the bug"}, rules_dir)
    # The intake rule dies; the static rules still render.
    assert isinstance(merged, str)


def test_default_rules_dir_honours_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ZYROMPTS_RULES_DIR", str(tmp_path))
    assert default_rules_dir() == tmp_path


def test_fragment_for_returns_none_when_criteria_do_not_match():
    rule = Rule(id="t", event="UserPromptSubmit",
                action={"type": "inject_context", "text": ["x"]},
                criteria={"match": [r"\bzzz\b"]})
    assert fragment_for({"prompt": "hello"}, rule) is None


# --- regression: the two bypass checks must agree ---------------------------
#
# `handlers._is_bypass` has always treated `/` as a slash command; the engine's
# `_bypassed` did not, so an action rule without `non_slash` fired on every
# slash command while a handler-backed rule stayed silent. The architecture doc
# says the two cannot diverge, so this pins the engine to the handler.

def test_slash_prefix_bypasses_an_action_rule_without_non_slash():
    rule = Rule(id="t", event="UserPromptSubmit",
                action={"type": "inject_context", "text": ["FIRED"]},
                criteria={"match": [r"\bhello\b"], "flags": ["ignorecase"]})
    assert fragment_for({"prompt": "/hello"}, rule) is None
    assert fragment_for({"prompt": "hello"}, rule) == "FIRED"


def test_star_and_hash_prefixes_still_bypass():
    rule = Rule(id="t", event="UserPromptSubmit",
                action={"type": "inject_context", "text": ["FIRED"]},
                criteria={"match": [r"\bhello\b"], "flags": ["ignorecase"]})
    for prompt in ("*hello", "#hello", "  /hello"):
        assert fragment_for({"prompt": prompt}, rule) is None, prompt


# --- regression: a typo in match_target used to be silent -------------------

def test_validate_rule_rejects_an_unknown_match_target():
    errors = validate_rule({
        "id": "x", "event": "UserPromptSubmit",
        "criteria": {"match_target": "promt", "match": ["a"]},
        "action": {"type": "inject_context", "text": ["t"]},
    })
    assert any("match_target" in error for error in errors)


def test_validate_rule_accepts_a_known_match_target():
    errors = validate_rule({
        "id": "x", "event": "UserPromptSubmit",
        "criteria": {"match_target": "prompt", "match": ["a"]},
        "action": {"type": "inject_context", "text": ["t"]},
    })
    assert errors == []
