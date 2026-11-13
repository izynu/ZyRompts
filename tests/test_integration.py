"""End-to-end behaviour: the parts must work together, not just alone.

These tests run the CLI the way a user or a platform harness does, and assert on
the contract each entry point promises. A unit test can pass while the wiring is
broken; this file is where wiring gets caught.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CORE = REPO / "core"


def run_cli(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(CORE)
    env.pop("ZYROMPTS_RULES_DIR", None)
    return subprocess.run(
        [sys.executable, "-m", "zyrompts", *args],
        input=stdin, capture_output=True, text=True, env=env, cwd=str(REPO), timeout=60)


def run_hook(event: str, payload: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(CORE)
    env.pop("ZYROMPTS_RULES_DIR", None)
    return subprocess.run(
        [sys.executable, "-m", "zyrompts.hooks", event],
        input=json.dumps(payload), capture_output=True, text=True,
        env=env, cwd=str(REPO), timeout=60)


# --- CLI -------------------------------------------------------------------

def test_health_reports_ok():
    result = run_cli("health")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["healthy"] is True
    assert payload["rules"] > 0
    assert payload["skills"] > 0


def test_no_subcommand_defaults_to_health():
    result = run_cli()
    assert result.returncode == 0
    assert "healthy" in result.stdout


def test_classify_json_shape():
    result = run_cli("classify", "refactor the payment module into separate services")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["workflow"] == "planned"


def test_policy_denies_a_root_delete():
    """A bare command argument is read as a shell command, not a tool name."""
    result = run_cli("policy", "rm -rf /", "--autonomy", "yolo")
    payload = json.loads(result.stdout)
    assert payload["decision"] == "deny"
    assert result.returncode == 1


def test_policy_accepts_the_explicit_tool_form():
    result = run_cli("policy", "Bash", '{"command": "rm -rf /"}', "--autonomy", "yolo")
    assert json.loads(result.stdout)["decision"] == "deny"


def test_policy_protected_path_denies_through_the_cli():
    result = run_cli("policy", "Write", '{"file_path": "/etc/passwd"}', "--autonomy", "yolo")
    assert json.loads(result.stdout)["decision"] == "deny"


def test_policy_allows_a_read_only_command():
    result = run_cli("policy", "ls -la", "--autonomy", "ask")
    assert "allow" in result.stdout.lower()


def test_redact_strips_a_key_from_stdin():
    secret = "sk-" + "a" * 32
    result = run_cli("redact", stdin=f"the key is {secret}\n")
    assert secret not in result.stdout
    assert "redact" in result.stdout.lower() or "sk-" not in result.stdout


def test_score_reports_a_grade():
    result = run_cli("score", "fix the bug")
    payload = json.loads(result.stdout)
    assert payload["grade"] == "F"
    # Exit 1 on a poor grade is the contract: the CLI is usable as a gate.
    assert result.returncode == 1


def test_score_exits_zero_for_a_strong_prompt():
    result = run_cli("score",
                     "Implement a rate limiter in src/api/limiter.py using Redis. "
                     "Acceptance: 429 after 100 req/min. Output: unified diff. "
                     "Do not modify other files.")
    assert result.returncode == 0
    assert json.loads(result.stdout)["grade"] == "A"


def test_decorum_prints_the_policy():
    result = run_cli("decorum")
    assert result.returncode == 0
    assert "Truth" in result.stdout


def test_decorum_check_flags_an_em_dash():
    result = run_cli("decorum", "--check", "It works — mostly.")
    assert "em dash" in result.stdout.lower()


def test_validate_passes_on_this_repo():
    result = run_cli("validate")
    assert result.returncode == 0, result.stdout + result.stderr


def test_eval_runs_every_suite_and_passes():
    result = run_cli("eval")
    assert result.returncode == 0, result.stdout + result.stderr
    for suite in ("classification", "policy", "prompt_score", "injection"):
        assert suite in result.stdout


def test_adapters_dry_run_lists_all_targets():
    result = run_cli("adapters")
    assert result.returncode == 0
    for target in ("claude-code", "gemini", "copilot", "codex", "opencode"):
        assert target in result.stdout


def test_plan_critique_blocks_an_empty_plan(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("", encoding="utf-8")
    result = run_cli("plan-critique", str(plan))
    assert result.returncode != 0 or "block" in result.stdout.lower()


# --- hooks -----------------------------------------------------------------

def test_hook_emits_valid_json_for_a_real_prompt():
    result = run_hook("UserPromptSubmit", {"prompt": "fix the bug"})
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "INTAKE" in payload["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize("prompt", ["*skip", "#remember this", "/command",
                                    "<task-notification> done"])
def test_hook_is_silent_for_bypass_and_machine_events(prompt):
    result = run_hook("UserPromptSubmit", {"prompt": prompt})
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_hook_is_silent_on_an_unknown_event():
    result = run_hook("NoSuchEvent", {"prompt": "hi"})
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_hook_is_silent_on_garbage_stdin():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(CORE)
    result = subprocess.run(
        [sys.executable, "-m", "zyrompts.hooks", "UserPromptSubmit"],
        input="{not json", capture_output=True, text=True, env=env,
        cwd=str(REPO), timeout=60)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_hook_is_silent_on_empty_stdin():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(CORE)
    result = subprocess.run(
        [sys.executable, "-m", "zyrompts.hooks", "UserPromptSubmit"],
        input="", capture_output=True, text=True, env=env, cwd=str(REPO), timeout=60)
    assert result.returncode == 0


def test_pretool_hook_warns_on_a_destructive_command():
    result = run_hook("PreToolUse", {"tool_name": "Bash",
                                     "tool_input": {"command": "rm -rf build"}})
    assert result.returncode == 0
    assert result.stdout.strip()


def test_session_start_hook_emits_decorum():
    result = run_hook("SessionStart", {"source": "startup"})
    assert result.returncode == 0
    assert "Truth" in result.stdout


# --- cross-cutting ---------------------------------------------------------

def test_cli_never_traces_on_a_bad_argument():
    result = run_cli("policy")
    # argparse exits 2 for a missing required arg; it must not traceback.
    assert "Traceback" not in result.stderr


def test_every_documented_event_has_a_working_hook():
    for event, payload in (
        ("UserPromptSubmit", {"prompt": "fix the bug"}),
        ("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "rm -rf x"}}),
        ("SessionStart", {"source": "startup"}),
        ("SubagentStart", {"agent_type": "researcher"}),
        ("Stop", {"transcript_path": ""}),
    ):
        result = run_hook(event, payload)
        assert result.returncode == 0, f"{event} exited {result.returncode}"


def test_redact_reads_stdin_when_no_argument_is_given():
    """`zyrompts redact < log` is the documented form; it must not be an error."""
    secret = "ghp_" + "b" * 36
    result = run_cli("redact", stdin=f"token: {secret}\n")
    assert result.returncode == 0, result.stderr
    assert secret not in result.stdout
    assert "github_token" in result.stdout
