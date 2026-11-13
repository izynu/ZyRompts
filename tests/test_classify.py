"""Classification contract: cheap by default, never cheap enough to be wrong."""

from __future__ import annotations

import pytest

from zyrompts.classify import (
    Complexity,
    Intent,
    Workflow,
    classify,
    choose_workflow,
    has_anchor,
)


def test_empty_prompt_is_direct_and_unknown():
    result = classify("")
    assert result.intent is Intent.UNKNOWN
    assert result.complexity is Complexity.TRIVIAL
    assert result.workflow is Workflow.DIRECT


def test_non_string_input_does_not_raise():
    assert classify(None).intent is Intent.UNKNOWN  # type: ignore[arg-type]
    assert classify(123).intent is Intent.UNKNOWN  # type: ignore[arg-type]


@pytest.mark.parametrize("prompt", [
    "fix TypeError in src/components/Map.tsx line 127",
    "add a --verbose flag to scripts/build.py",
])
def test_anchored_small_change_is_direct(prompt):
    assert classify(prompt).workflow is Workflow.DIRECT


def test_unanchored_fix_is_not_direct():
    """`fix the bug` has no target. DIRECT would mean guessing which bug."""
    result = classify("fix the bug")
    assert result.intent is Intent.FIX
    assert result.workflow is Workflow.LIGHT
    assert "ambiguous" in result.flags


def test_terse_but_wide_is_not_clamped_to_small():
    """Regression: a 7-word wide-scope request used to clamp to `small`."""
    result = classify("refactor the payment module into separate services")
    assert result.complexity is Complexity.MODERATE
    assert result.workflow is Workflow.PLANNED


def test_named_architectural_scope_scores_large():
    result = classify("migrate the monolith to microservices")
    assert result.complexity.rank >= Complexity.LARGE.rank
    assert result.workflow in (Workflow.PLANNED, Workflow.FULL)


@pytest.mark.parametrize("prompt,intent", [
    ("why does the build fail on arm64", Intent.QUESTION),
    ("what is a monad", Intent.EXPLAIN),
    ("explain how the auth middleware works", Intent.EXPLAIN),
    ("do a security review of the upload endpoint", Intent.REVIEW),
])
def test_opener_beats_verb_table(prompt, intent):
    """`why ... fail` is a diagnosis request, not a patch instruction."""
    assert classify(prompt).intent is intent


def test_how_do_i_is_an_action_request():
    assert classify("how do I add a rate limiter to the API").intent is Intent.BUILD


@pytest.mark.parametrize("prompt,expected", [
    ("fix the bug", False),
    ("fix TypeError in src/components/Map.tsx line 127", True),
    ("the login endpoint returns 500", False),
    ("make `parse_date` accept ISO-8601", True),
    ("refactor UserService and OrderRepo", True),
])
def test_has_anchor(prompt, expected):
    assert has_anchor(prompt) is expected


def test_complexity_enum_ordering_is_ranked_not_lexical():
    """These are str enums, so `>=` compares labels unless rank is used."""
    assert Complexity.TRIVIAL.at_least(Complexity.MODERATE) is False
    assert Complexity.LARGE.at_least(Complexity.MODERATE) is True
    assert Complexity.TRIVIAL.rank < Complexity.EPIC.rank


def test_choose_workflow_floor_never_lowers_a_heavy_tier():
    tier = choose_workflow(Intent.BUILD, Complexity.EPIC, [], has_target=False)
    assert tier is Workflow.FULL


def test_machine_event_is_not_classified_as_a_user_request():
    result = classify("<task-notification> agent finished")
    assert result.workflow is Workflow.DIRECT
