"""Workflow contract: the lifecycle is gated, and a gate fails closed.

The regression this file exists for: BLOCKED used to be outside the phase list,
so the next advance() treated the workflow as finished and jumped to DONE,
skipping plan, critique and approval entirely.
"""

from __future__ import annotations

import pytest

from zyrompts.classify import Workflow
from zyrompts.workflow import TIER_PHASES, Gate, Phase, start


def test_each_tier_has_a_distinct_length():
    lengths = {tier: len(phases) for tier, phases in TIER_PHASES.items()}
    assert lengths[Workflow.DIRECT] < lengths[Workflow.LIGHT]
    assert lengths[Workflow.LIGHT] < lengths[Workflow.PLANNED]
    assert lengths[Workflow.PLANNED] < lengths[Workflow.FULL]


def test_full_tier_contains_the_24_step_core_phases():
    phases = set(TIER_PHASES[Workflow.FULL])
    for required in (Phase.CLARIFY, Phase.RESEARCH, Phase.SPECIFY, Phase.PLAN,
                     Phase.CRITIQUE, Phase.APPROVE, Phase.IMPLEMENT, Phase.REVIEW,
                     Phase.FIX, Phase.VERIFY, Phase.ARCHIVE, Phase.DONE):
        assert required in phases


def test_simple_request_does_not_enter_the_full_lifecycle():
    state = start(Workflow.DIRECT)
    assert Phase.PLAN not in state.phases
    assert Phase.CRITIQUE not in state.phases


def test_met_gates_advance_in_order():
    state = start(Workflow.LIGHT)
    assert state.phase is Phase.INTAKE
    state.set_gates(Phase.INTAKE, [Gate("ready", satisfied=True)])
    assert state.advance() is Phase.IMPLEMENT


def test_unmet_gate_blocks():
    state = start(Workflow.LIGHT)
    state.set_gates(Phase.INTAKE, [Gate("ready", satisfied=False)])
    assert state.advance() is Phase.BLOCKED


def test_blocked_is_not_terminal_and_retries_the_same_phase():
    """Regression: a block used to advance straight to DONE."""
    state = start(Workflow.PLANNED)
    state.set_gates(Phase.INTAKE, [Gate("ready", satisfied=False)])
    state.advance()
    assert state.phase is Phase.BLOCKED

    for _ in range(5):
        state.advance()
        assert state.phase is Phase.BLOCKED, "a blocked workflow must stay blocked"

    state.gates["intake"][0].satisfied = True
    assert state.advance() is Phase.CLARIFY


def test_approval_is_required_before_implement():
    state = start(Workflow.PLANNED)
    for gates in state.gates.values():
        for gate in gates:
            gate.satisfied = True
    # Walk to APPROVE.
    for _ in range(len(state.phases)):
        if state.phase is Phase.APPROVE:
            break
        state.advance()
    assert state.phase is Phase.APPROVE

    assert state.advance() is Phase.BLOCKED
    state.approve(True)
    assert state.advance() is Phase.IMPLEMENT


def test_denied_approval_keeps_it_blocked():
    state = start(Workflow.PLANNED)
    state.phase = Phase.APPROVE
    state.approve(False)
    assert state.advance() is Phase.BLOCKED


def test_approval_can_be_disabled_explicitly():
    """Disabling approval means the gate must be satisfied by other evidence."""
    state = start(Workflow.PLANNED)
    state.phase = Phase.APPROVE
    state.approval_required = False
    for gate in state.gates["approve"]:
        gate.satisfied = True
    assert state.advance() is Phase.IMPLEMENT


def test_critique_loop_is_bounded():
    state = start(Workflow.PLANNED)
    state.phase = Phase.CRITIQUE
    seen = [state.loop_critique() for _ in range(state.max_critique)]
    assert Phase.APPROVE in seen
    assert state.critique_iterations == state.max_critique


def test_fix_loop_is_bounded_and_ends_at_verify():
    state = start(Workflow.FULL)
    state.phase = Phase.REVIEW
    seen = [state.loop_fix() for _ in range(state.max_fix)]
    assert Phase.VERIFY in seen


def test_history_records_every_transition():
    state = start(Workflow.LIGHT)
    state.set_gates(Phase.INTAKE, [Gate("ready", satisfied=True)])
    state.advance()
    kinds = [entry["event"] for entry in state.history]
    assert "advance" in kinds


def test_blocked_transition_is_recorded_with_a_reason():
    state = start(Workflow.LIGHT)
    state.set_gates(Phase.INTAKE, [Gate("ready", satisfied=False)])
    state.advance()
    blocked = [e for e in state.history if e["event"] == "blocked"]
    assert blocked and blocked[-1]["detail"]


def test_summary_reports_phase_and_progress():
    state = start(Workflow.PLANNED)
    summary = state.summary()
    assert summary["phase"] == "intake"
    assert summary["tier"] == "planned"


def test_to_markdown_names_the_phase():
    state = start(Workflow.LIGHT)
    assert "intake" in state.to_markdown()


def test_unknown_tier_phase_lookup_is_safe():
    state = start(Workflow.DIRECT)
    assert state.index(Phase.ARCHIVE) == -1
