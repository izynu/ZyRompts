"""Decorum and prompt-engineering contracts.

Decorum is enforced by text and by a checker; the checker is what makes the
policy testable. Prompt scoring is covered in depth by the eval suite, so this
file pins only the invariants a re-weighting must not break.
"""

from __future__ import annotations

import pytest

from zyrompts.decorum import DECORUM_VERSION, check_reply, render
from zyrompts.prompts import (
    Framework,
    detect_model_family,
    improve_prompt,
    score_prompt,
)


def test_render_contains_every_policy_section():
    text = render()
    for heading in ("Truth", "Uncertainty", "Disagreement", "Clarification",
                    "Style", "Limits"):
        assert heading in text


def test_render_can_omit_the_header():
    assert not render(include_header=False).startswith("#")


def test_decorum_version_is_declared():
    assert DECORUM_VERSION


@pytest.mark.parametrize("text", [
    "Done! All tests pass.",
    "I've fixed the bug and everything works.",
    "The build is complete.",
])
def test_unsupported_completion_claims_are_flagged(text):
    assert check_reply(text), f"missed completion claim: {text!r}"


def test_completion_claim_with_evidence_passes():
    text = "Done. `pytest tests/ -q` -> 181 passed in 0.76s."
    assert check_reply(text) == []


@pytest.mark.parametrize("text", [
    "Great question! Here is the answer.",
    "Certainly! I can help with that.",
])
def test_flattery_openers_are_flagged(text):
    assert check_reply(text)


def test_emoji_is_flagged():
    assert check_reply("The fix works 🎉")


def test_em_dash_is_flagged():
    assert check_reply("It works — mostly.")


def test_plain_technical_prose_passes():
    assert check_reply("The cache is warm. The second run took 40ms.") == []


def test_empty_reply_is_clean():
    assert check_reply("") == []


def test_score_is_bounded_and_attributable():
    breakdown = score_prompt("fix the bug")
    assert 0 <= breakdown.total <= breakdown.max_total <= 100
    assert set(breakdown.components) <= {
        "task_clarity", "target_context", "output_format", "constraints",
        "success_criteria", "scope_boundaries", "examples"}


def test_naming_a_target_raises_the_score():
    vague = score_prompt("fix the bug")
    targeted = score_prompt("fix TypeError in src/components/Map.tsx line 127")
    assert targeted.total > vague.total


def test_adding_acceptance_criteria_raises_the_score():
    before = score_prompt("Add a --verbose flag to scripts/build.py")
    after = score_prompt("Add a --verbose flag to scripts/build.py. "
                         "Acceptance: it prints one line per step.")
    assert after.total > before.total


def test_question_is_graded_on_a_smaller_denominator():
    breakdown = score_prompt("explain how the auth middleware works")
    assert "success_criteria" in breakdown.not_applicable
    assert breakdown.max_total < 100


def test_improve_prompt_marks_gaps_as_questions():
    improved = improve_prompt("fix the bug")
    assert improved.open_questions, "an underspecified prompt must produce questions"
    assert improved.after.total >= improved.before.total


def test_improve_prompt_never_invents_domain_facts():
    improved = improve_prompt("add a rate limiter to the API")
    assert "Redis" not in improved.improved


def test_improve_prompt_returns_a_framework():
    improved = improve_prompt("implement a rate limiter in src/api/limiter.py")
    assert isinstance(improved.framework, Framework)


@pytest.mark.parametrize("text,family", [
    ("claude-opus-5", "claude"),
    ("gpt-5-codex", "openai-reasoning"),
    ("gemini-3-pro", "gemini"),
    ("some-local-model", "local"),
    ("nothing recognisable", "unknown"),
])
def test_detect_model_family(text, family):
    assert detect_model_family(text).value == family
