"""Multi-agent registry and orchestrator.

Agents are declared as data (capability, inputs, outputs, limits) so the
orchestrator can route work without hardcoding names. The orchestrator owns the
policy that matters:

- an agent never approves its own output; review is always a different agent
- every delegation is bounded (attempt cap, token budget, wall clock)
- independent tasks run in parallel; dependent tasks run in order
- the orchestrator aggregates results and refuses to claim completion for any
  task whose agent reported unverified work
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from enum import Enum


class AgentRole(str, Enum):
    RESEARCHER = "researcher"
    PROMPT_ENGINEER = "prompt-engineer"
    PLANNER = "planner"
    ARCHITECT = "architect"
    CRITIC = "critic"
    DEVELOPER = "developer"
    DEBUGGER = "debugger"
    TESTER = "tester"
    CODE_REVIEWER = "code-reviewer"
    SECURITY_REVIEWER = "security-reviewer"
    DOCUMENTATION = "documentation"
    PERFORMANCE = "performance"
    VERIFIER = "verifier"


class ModelTier(str, Enum):
    """Route by capability need, not by product name."""

    FRONTIER = "frontier"   # planning, architecture, adversarial review
    STANDARD = "standard"   # implementation, debugging
    FAST = "fast"           # search, extraction, mechanical edits


@dataclass(frozen=True)
class AgentSpec:
    role: AgentRole
    purpose: str
    tier: ModelTier
    tools: tuple[str, ...]
    read_only: bool = True
    max_attempts: int = 2
    can_review: tuple[AgentRole, ...] = ()
    produces: str = ""

    def to_dict(self) -> dict:
        return {
            "role": self.role.value,
            "purpose": self.purpose,
            "tier": self.tier.value,
            "tools": list(self.tools),
            "read_only": self.read_only,
            "max_attempts": self.max_attempts,
            "can_review": [r.value for r in self.can_review],
            "produces": self.produces,
        }


REGISTRY: dict[AgentRole, AgentSpec] = {
    AgentRole.RESEARCHER: AgentSpec(
        AgentRole.RESEARCHER,
        "Gather evidence from the codebase, docs and the web; return conclusions with citations.",
        ModelTier.FAST, ("Read", "Glob", "Grep", "WebSearch", "WebFetch"),
        produces="research report with sources"),
    AgentRole.PROMPT_ENGINEER: AgentSpec(
        AgentRole.PROMPT_ENGINEER,
        "Classify, score and rewrite a request into a precise, model-aware prompt.",
        ModelTier.STANDARD, ("Read",),
        produces="improved prompt with before/after score"),
    AgentRole.PLANNER: AgentSpec(
        AgentRole.PLANNER,
        "Turn requirements into ordered chapters, each with affected files and verification.",
        ModelTier.FRONTIER, ("Read", "Glob", "Grep"),
        produces="plan.md"),
    AgentRole.ARCHITECT: AgentSpec(
        AgentRole.ARCHITECT,
        "Decide structure, boundaries and interfaces; compare alternatives with tradeoffs.",
        ModelTier.FRONTIER, ("Read", "Glob", "Grep"),
        produces="architecture decision with alternatives"),
    AgentRole.CRITIC: AgentSpec(
        AgentRole.CRITIC,
        "Adversarially refute a plan or design; report only findings that survive refutation.",
        ModelTier.FRONTIER, ("Read", "Glob", "Grep", "Bash"),
        can_review=(AgentRole.PLANNER, AgentRole.ARCHITECT),
        produces="critique with CONFIRMED/UNVERIFIED findings"),
    AgentRole.DEVELOPER: AgentSpec(
        AgentRole.DEVELOPER,
        "Implement the approved plan step by step, tests first where a suite exists.",
        ModelTier.STANDARD, ("Read", "Write", "Edit", "Bash", "Glob", "Grep"),
        read_only=False,
        produces="code changes with test evidence"),
    AgentRole.DEBUGGER: AgentSpec(
        AgentRole.DEBUGGER,
        "Find the root cause from the error, not the symptom; prove it before fixing.",
        ModelTier.STANDARD, ("Read", "Grep", "Bash"),
        produces="root cause with reproduction"),
    AgentRole.TESTER: AgentSpec(
        AgentRole.TESTER,
        "Write failing tests first, then confirm they pass; never edit a test to fit code.",
        ModelTier.STANDARD, ("Read", "Write", "Bash"),
        read_only=False,
        can_review=(AgentRole.DEVELOPER,),
        produces="test suite and run output"),
    AgentRole.CODE_REVIEWER: AgentSpec(
        AgentRole.CODE_REVIEWER,
        "Review a diff for correctness, reuse, simplification and convention drift.",
        ModelTier.FRONTIER, ("Read", "Grep", "Bash"),
        can_review=(AgentRole.DEVELOPER, AgentRole.TESTER),
        produces="findings ranked by severity"),
    AgentRole.SECURITY_REVIEWER: AgentSpec(
        AgentRole.SECURITY_REVIEWER,
        "Hunt injection, secret leakage, unsafe deserialization and permission gaps.",
        ModelTier.FRONTIER, ("Read", "Grep", "Bash"),
        can_review=(AgentRole.DEVELOPER,),
        produces="security findings with severity and fix"),
    AgentRole.DOCUMENTATION: AgentSpec(
        AgentRole.DOCUMENTATION,
        "Write docs that match the code as it is, with runnable examples.",
        ModelTier.FAST, ("Read", "Write", "Glob"),
        read_only=False,
        produces="docs update"),
    AgentRole.PERFORMANCE: AgentSpec(
        AgentRole.PERFORMANCE,
        "Measure before optimizing; report the benchmark that justifies the change.",
        ModelTier.STANDARD, ("Read", "Bash"),
        produces="measurement and optimization proposal"),
    AgentRole.VERIFIER: AgentSpec(
        AgentRole.VERIFIER,
        "Independently confirm every acceptance criterion against evidence.",
        ModelTier.FRONTIER, ("Read", "Bash", "Grep"),
        can_review=(AgentRole.DEVELOPER, AgentRole.TESTER, AgentRole.CODE_REVIEWER),
        produces="acceptance matrix with pass/fail evidence"),
}


@dataclass
class Delegation:
    id: str
    role: AgentRole
    task: str
    depends_on: list[str] = field(default_factory=list)
    attempts: int = 0
    status: str = "pending"     # pending | running | done | failed | blocked
    result: str = ""
    verified: bool = False
    cost_tokens: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role.value,
            "task": self.task,
            "depends_on": list(self.depends_on),
            "attempts": self.attempts,
            "status": self.status,
            "verified": self.verified,
            "cost_tokens": self.cost_tokens,
            "result": self.result,
        }


class Orchestrator:
    """Plan, dispatch and aggregate bounded agent work."""

    def __init__(self, max_parallel: int = 4, token_budget: int = 0):
        self.delegations: list[Delegation] = []
        self.max_parallel = max(1, max_parallel)
        self.token_budget = token_budget
        self._counter = itertools.count(1)

    # --- planning -----------------------------------------------------------

    def add(self, role: AgentRole, task: str, depends_on: list[str] | None = None) -> Delegation:
        delegation = Delegation(
            id=f"d{next(self._counter)}",
            role=role,
            task=task,
            depends_on=depends_on or [],
        )
        self.delegations.append(delegation)
        return delegation

    def spec(self, role: AgentRole) -> AgentSpec:
        return REGISTRY[role]

    # --- scheduling ---------------------------------------------------------

    def ready(self) -> list[Delegation]:
        done = {d.id for d in self.delegations if d.status == "done"}
        return [d for d in self.delegations
                if d.status == "pending" and all(dep in done for dep in d.depends_on)]

    def next_batch(self) -> list[Delegation]:
        """Return the next runnable batch, capped at max_parallel.

        Within a batch, prefer read-only work so the batch cannot conflict on
        the filesystem; a batch with any writer is capped at one.
        """
        candidates = self.ready()
        if not candidates:
            return []
        writers = [d for d in candidates if not REGISTRY[d.role].read_only]
        if writers:
            return writers[:1]
        return candidates[:self.max_parallel]

    def blocked(self) -> list[Delegation]:
        """Pending delegations whose dependencies can no longer succeed."""
        failed = {d.id for d in self.delegations if d.status in ("failed", "blocked")}
        return [d for d in self.delegations
                if d.status == "pending" and any(dep in failed for dep in d.depends_on)]

    # --- execution bookkeeping ---------------------------------------------

    def start(self, delegation_id: str) -> Delegation | None:
        for delegation in self.delegations:
            if delegation.id == delegation_id:
                if delegation.attempts >= REGISTRY[delegation.role].max_attempts:
                    delegation.status = "failed"
                    delegation.result = "attempt limit reached"
                    return delegation
                delegation.attempts += 1
                delegation.status = "running"
                return delegation
        return None

    def finish(self, delegation_id: str, result: str, verified: bool = False,
               cost_tokens: int = 0) -> Delegation | None:
        for delegation in self.delegations:
            if delegation.id == delegation_id:
                delegation.status = "done"
                delegation.result = result
                delegation.verified = verified
                delegation.cost_tokens += cost_tokens
                return delegation
        return None

    def fail(self, delegation_id: str, reason: str) -> Delegation | None:
        for delegation in self.delegations:
            if delegation.id == delegation_id:
                spec = REGISTRY[delegation.role]
                if delegation.attempts < spec.max_attempts:
                    delegation.status = "pending"
                    delegation.result = f"retry after: {reason}"
                else:
                    delegation.status = "failed"
                    delegation.result = reason
                return delegation
        return None

    # --- review integrity ---------------------------------------------------

    def review_pairs(self) -> list[tuple[str, str]]:
        """Return (producer, reviewer) pairs that must be independent.

        An agent may never review its own output. Where a role has no declared
        reviewer, the verifier is used.
        """
        pairs: list[tuple[str, str]] = []
        for delegation in self.delegations:
            if delegation.status != "done":
                continue
            spec = REGISTRY[delegation.role]
            reviewers = spec.can_review or (AgentRole.VERIFIER,)
            reviewer = next((r for r in reviewers if r is not delegation.role), AgentRole.VERIFIER)
            pairs.append((delegation.id, reviewer.value))
        return pairs

    # --- aggregation --------------------------------------------------------

    def summary(self) -> dict:
        counts: dict[str, int] = {}
        for delegation in self.delegations:
            counts[delegation.status] = counts.get(delegation.status, 0) + 1
        total_cost = sum(d.cost_tokens for d in self.delegations)
        unverified = [d.id for d in self.delegations
                      if d.status == "done" and not d.verified]
        return {
            "delegations": len(self.delegations),
            "by_status": counts,
            "blocked": len(self.blocked()),
            "unverified": unverified,
            "tokens": total_cost,
            "over_budget": bool(self.token_budget and total_cost > self.token_budget),
            "complete": (all(d.status == "done" for d in self.delegations)
                         and not unverified),
        }
