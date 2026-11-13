"""Agent orchestration contract.

The load-bearing property: an agent never reviews its own output, and the
orchestrator never schedules a reviewer concurrently with the writer whose
output it is reviewing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zyrompts.agents import REGISTRY, AgentRole, ModelTier, Orchestrator


def test_every_role_has_a_spec():
    for role in AgentRole:
        assert role in REGISTRY, f"{role} has no AgentSpec"


def test_writers_are_not_read_only():
    for role in (AgentRole.DEVELOPER, AgentRole.TESTER):
        assert REGISTRY[role].read_only is False


def test_debugger_is_read_only_because_it_has_no_write_tool():
    """A debugger diagnoses; the fix is the developer's step."""
    spec = REGISTRY[AgentRole.DEBUGGER]
    assert spec.read_only is True
    assert "Write" not in spec.tools


def test_reviewers_are_read_only():
    for role in (AgentRole.CRITIC, AgentRole.CODE_REVIEWER, AgentRole.SECURITY_REVIEWER):
        assert REGISTRY[role].read_only is True


def test_no_agent_can_review_itself():
    for role, spec in REGISTRY.items():
        assert role not in spec.can_review, f"{role} may review its own output"


def test_review_pairs_never_pair_a_role_with_itself():
    orchestrator = Orchestrator()
    producer = orchestrator.add(AgentRole.DEVELOPER, "write it")
    pairs = orchestrator.review_pairs()
    for pair in pairs:
        assert pair[0] != pair[1]


def test_add_returns_a_pending_delegation():
    orchestrator = Orchestrator()
    delegation = orchestrator.add(AgentRole.RESEARCHER, "find the docs")
    assert delegation.status == "pending"
    assert delegation.role is AgentRole.RESEARCHER


def test_dependencies_gate_readiness():
    orchestrator = Orchestrator()
    first = orchestrator.add(AgentRole.PLANNER, "plan")
    second = orchestrator.add(AgentRole.DEVELOPER, "build", depends_on=[first.id])
    ready_ids = [d.id for d in orchestrator.ready()]
    assert first.id in ready_ids
    assert second.id not in ready_ids

    orchestrator.start(first.id)
    orchestrator.finish(first.id, "plan done", verified=True)
    assert second.id in [d.id for d in orchestrator.ready()]


def test_next_batch_respects_max_parallel():
    orchestrator = Orchestrator(max_parallel=2)
    for i in range(5):
        orchestrator.add(AgentRole.RESEARCHER, f"task {i}")
    assert len(orchestrator.next_batch()) <= 2


def test_next_batch_never_runs_a_writer_and_its_reviewer_together():
    orchestrator = Orchestrator(max_parallel=8)
    orchestrator.add(AgentRole.DEVELOPER, "write it")
    batch = orchestrator.next_batch()
    roles = {d.role for d in batch}
    assert not ({AgentRole.DEVELOPER, AgentRole.CODE_REVIEWER} <= roles)


def test_fail_retries_while_attempts_remain():
    orchestrator = Orchestrator()
    delegation = orchestrator.add(AgentRole.PLANNER, "plan")
    orchestrator.start(delegation.id)
    orchestrator.fail(delegation.id, "no spec")
    assert delegation.status == "pending"
    assert "retry after" in delegation.result


def test_exhausted_delegation_blocks_its_dependents():
    orchestrator = Orchestrator()
    first = orchestrator.add(AgentRole.PLANNER, "plan")
    second = orchestrator.add(AgentRole.DEVELOPER, "build", depends_on=[first.id])
    spec = REGISTRY[AgentRole.PLANNER]
    for _ in range(spec.max_attempts):
        orchestrator.start(first.id)
        orchestrator.fail(first.id, "no spec")
    assert first.status == "failed"
    assert second.id in [d.id for d in orchestrator.blocked()]
    assert second.id not in [d.id for d in orchestrator.ready()]


def test_exhausted_delegation_is_not_ready():
    orchestrator = Orchestrator()
    delegation = orchestrator.add(AgentRole.RESEARCHER, "x")
    for _ in range(REGISTRY[AgentRole.RESEARCHER].max_attempts):
        orchestrator.start(delegation.id)
        orchestrator.fail(delegation.id, "boom")
    assert delegation.status == "failed"
    assert delegation.id not in [d.id for d in orchestrator.ready()]


def test_start_records_an_attempt():
    orchestrator = Orchestrator()
    delegation = orchestrator.add(AgentRole.RESEARCHER, "x")
    orchestrator.start(delegation.id)
    assert delegation.attempts == 1
    assert delegation.status == "running"


def test_finish_marks_status_and_verification():
    orchestrator = Orchestrator()
    delegation = orchestrator.add(AgentRole.RESEARCHER, "x")
    orchestrator.start(delegation.id)
    orchestrator.finish(delegation.id, "result", verified=True, cost_tokens=100)
    assert delegation.status == "done"
    assert delegation.verified is True
    assert delegation.cost_tokens == 100


def test_unknown_id_returns_none():
    orchestrator = Orchestrator()
    assert orchestrator.start("nope") is None
    assert orchestrator.finish("nope", "x") is None
    assert orchestrator.fail("nope", "x") is None


def test_summary_counts_by_status():
    orchestrator = Orchestrator()
    a = orchestrator.add(AgentRole.RESEARCHER, "a")
    orchestrator.add(AgentRole.PLANNER, "b")
    orchestrator.start(a.id)
    orchestrator.finish(a.id, "done", verified=True)
    summary = orchestrator.summary()
    assert summary["delegations"] == 2
    assert summary["by_status"]["done"] == 1


def test_spec_lookup_returns_the_registered_spec():
    orchestrator = Orchestrator()
    spec = orchestrator.spec(AgentRole.SECURITY_REVIEWER)
    assert spec.role is AgentRole.SECURITY_REVIEWER
    assert spec.tier in tuple(ModelTier)


# --- markdown role contracts ------------------------------------------------

AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"


def _contract(name: str) -> dict[str, str]:
    text = (AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    front = text.split("---")[1]
    fields: dict[str, str] = {}
    for line in front.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


@pytest.mark.parametrize("name,role", [
    ("researcher", AgentRole.RESEARCHER),
    ("planner", AgentRole.PLANNER),
    ("critic", AgentRole.CRITIC),
    ("implementer", AgentRole.DEVELOPER),
    ("test-reviewer", AgentRole.TESTER),
    ("security-reviewer", AgentRole.SECURITY_REVIEWER),
])
def test_markdown_contract_matches_the_registry(name, role):
    """The docs and the code are two copies of one fact; they must agree."""
    contract = _contract(name)
    spec = REGISTRY[role]
    assert contract["role"] == spec.role.value
    assert contract["tier"] == spec.tier.value
    assert contract["read-only"] == str(spec.read_only).lower()
    assert contract["produces"] == spec.produces
    assert [t.strip() for t in contract["tools"].split(",")] == list(spec.tools)


def test_every_agent_contract_states_its_version():
    for path in AGENTS_DIR.glob("*.md"):
        assert "## Version" in path.read_text(encoding="utf-8"), path.name
