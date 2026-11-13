"""The lifecycle: a resumable, bounded state machine.

This is the part that turns a pile of skills into a system. Every phase is
declared with its entry conditions, its exit evidence, and whether it can be
skipped. The machine refuses to advance without evidence, refuses to loop
forever, and persists after every transition so a crash is recoverable.

The 24-step lifecycle from the design is compressed into phases, because a
literal 24-state machine is mostly ceremony for simple work. The mapping is
recorded in PHASE_STEPS so the checklist stays traceable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .classify import Workflow


class Phase(str, Enum):
    INTAKE = "intake"
    CLARIFY = "clarify"
    RESEARCH = "research"
    SPECIFY = "specify"
    PLAN = "plan"
    CRITIQUE = "critique"
    APPROVE = "approve"
    IMPLEMENT = "implement"
    REVIEW = "review"
    FIX = "fix"
    VERIFY = "verify"
    ARCHIVE = "archive"
    DONE = "done"
    BLOCKED = "blocked"


# Which of the 24 canonical lifecycle steps each phase covers.
PHASE_STEPS: dict[Phase, tuple[int, ...]] = {
    Phase.INTAKE: (1, 2, 3, 4),
    Phase.CLARIFY: (5, 6, 7),
    Phase.RESEARCH: (6,),
    Phase.SPECIFY: (8, 9),
    Phase.PLAN: (10,),
    Phase.CRITIQUE: (11, 12),
    Phase.APPROVE: (13,),
    Phase.IMPLEMENT: (14, 15, 16),
    Phase.REVIEW: (17, 18),
    Phase.FIX: (19, 20),
    Phase.VERIFY: (21, 22),
    Phase.ARCHIVE: (23,),
    Phase.DONE: (24,),
    Phase.BLOCKED: (),
}

# Ordered phase lists per workflow tier. Cheap tiers skip the expensive phases.
TIER_PHASES: dict[Workflow, list[Phase]] = {
    Workflow.DIRECT: [Phase.INTAKE, Phase.DONE],
    Workflow.LIGHT: [Phase.INTAKE, Phase.IMPLEMENT, Phase.VERIFY, Phase.DONE],
    Workflow.PLANNED: [Phase.INTAKE, Phase.CLARIFY, Phase.SPECIFY, Phase.PLAN,
                       Phase.CRITIQUE, Phase.APPROVE, Phase.IMPLEMENT,
                       Phase.REVIEW, Phase.VERIFY, Phase.DONE],
    Workflow.FULL: [Phase.INTAKE, Phase.CLARIFY, Phase.RESEARCH, Phase.SPECIFY,
                    Phase.PLAN, Phase.CRITIQUE, Phase.APPROVE, Phase.IMPLEMENT,
                    Phase.REVIEW, Phase.FIX, Phase.VERIFY, Phase.ARCHIVE, Phase.DONE],
}


@dataclass
class Gate:
    """An exit condition for a phase."""

    description: str
    satisfied: bool = False
    evidence: str = ""


@dataclass
class WorkflowState:
    tier: Workflow
    phase: Phase = Phase.INTAKE
    history: list[dict] = field(default_factory=list)
    gates: dict[str, list[Gate]] = field(default_factory=dict)
    critique_iterations: int = 0
    fix_iterations: int = 0
    max_critique: int = 3
    max_fix: int = 2
    approval_required: bool = True
    approved: bool = False
    # The phase a block interrupted. BLOCKED is not a member of `phases`, so
    # without this the index lookup fails, `next_phase()` returns None, and the
    # next advance() reads that as "finished" and jumps to DONE. A gate meant to
    # fail closed would fail open.
    resume_at: Phase | None = None

    # --- navigation ---------------------------------------------------------

    @property
    def phases(self) -> list[Phase]:
        return TIER_PHASES[self.tier]

    def index(self, phase: Phase | None = None) -> int:
        phase = phase or self.phase
        if phase is Phase.BLOCKED and self.resume_at is not None:
            return self.phases.index(self.resume_at) if self.resume_at in self.phases else -1
        try:
            return self.phases.index(phase)
        except ValueError:
            return -1

    def next_phase(self) -> Phase | None:
        current = self.index()
        if current < 0 or current + 1 >= len(self.phases):
            return None
        return self.phases[current + 1]

    def remaining(self) -> list[Phase]:
        current = self.index()
        return self.phases[current + 1:] if current >= 0 else []

    # --- gating -------------------------------------------------------------

    def set_gates(self, phase: Phase, gates: list[Gate]) -> None:
        self.gates[phase.value] = gates

    def unmet_gates(self, phase: Phase | None = None) -> list[Gate]:
        phase = phase or self.phase
        return [g for g in self.gates.get(phase.value, []) if not g.satisfied]

    def satisfy(self, phase: Phase, description_fragment: str, evidence: str) -> bool:
        for gate in self.gates.get(phase.value, []):
            if description_fragment.lower() in gate.description.lower():
                gate.satisfied = True
                gate.evidence = evidence
                return True
        return False

    # --- transitions --------------------------------------------------------

    def advance(self, evidence: str = "") -> Phase:
        """Move to the next phase, or BLOCKED if a gate is unmet.

        A block is not a terminal state: it records where to resume, so the next
        call retries the same gate rather than treating the workflow as finished.
        """
        if self.phase is Phase.BLOCKED:
            if self.resume_at is None:
                self._record("blocked", "no resume point; staying blocked")
                return self.phase
            self.phase = self.resume_at
            self.resume_at = None

        if self.phase is Phase.APPROVE and self.approval_required and not self.approved:
            return self._block("approval not granted")

        unmet = self.unmet_gates()
        if unmet:
            return self._block("; ".join(g.description for g in unmet))

        nxt = self.next_phase()
        if nxt is None:
            self._record("done", evidence)
            self.phase = Phase.DONE
            return self.phase

        self._record("advance", evidence or f"{self.phase.value} -> {nxt.value}")
        self.phase = nxt
        return self.phase

    def _block(self, reason: str) -> Phase:
        """Enter BLOCKED, remembering the phase that must be retried."""
        if self.phase is not Phase.BLOCKED:
            self.resume_at = self.phase
        self._record("blocked", reason)
        self.phase = Phase.BLOCKED
        return self.phase

    def loop_critique(self) -> Phase:
        """Iterate critique -> plan within the bound, then go to approval."""
        self.critique_iterations += 1
        if self.critique_iterations >= self.max_critique:
            self._record("critique_limit", f"{self.critique_iterations} iterations")
            self.phase = Phase.APPROVE
            return self.phase
        self.phase = Phase.CRITIQUE
        return self.phase

    def loop_fix(self) -> Phase:
        """Iterate review -> fix within the bound, then verify regardless."""
        self.fix_iterations += 1
        if self.fix_iterations >= self.max_fix:
            self._record("fix_limit", f"{self.fix_iterations} iterations")
            self.phase = Phase.VERIFY
            return self.phase
        self.phase = Phase.FIX
        return self.phase

    def approve(self, approved: bool, note: str = "") -> None:
        self.approved = approved
        self._record("approval", note or ("granted" if approved else "denied"))
        if not approved:
            self.phase = Phase.BLOCKED

    def _record(self, event: str, detail: str) -> None:
        self.history.append({
            "phase": self.phase.value,
            "event": event,
            "detail": detail,
            "iteration": self.critique_iterations + self.fix_iterations,
        })

    # --- reporting ----------------------------------------------------------

    def summary(self) -> dict:
        return {
            "tier": self.tier.value,
            "phase": self.phase.value,
            "progress": f"{max(0, self.index()) + 1}/{len(self.phases)}",
            "critique_iterations": self.critique_iterations,
            "fix_iterations": self.fix_iterations,
            "approved": self.approved,
            "unmet_gates": [g.description for g in self.unmet_gates()],
            "history": list(self.history),
        }

    def to_markdown(self) -> str:
        lines = [f"# Workflow: {self.tier.value}", "",
                 f"Phase: {self.phase.value} ({self.summary()['progress']})", ""]
        for phase in self.phases:
            marker = "->" if phase is self.phase else ("x" if self.index(phase) < self.index() else " ")
            lines.append(f"{marker} {phase.value}")
            for gate in self.gates.get(phase.value, []):
                state = "ok" if gate.satisfied else "open"
                lines.append(f"    [{state}] {gate.description}"
                             + (f" ({gate.evidence})" if gate.evidence else ""))
        return "\n".join(lines) + "\n"


def start(tier: Workflow) -> WorkflowState:
    """Create a workflow at the cheapest tier that can still be correct."""
    state = WorkflowState(tier=tier)
    state.set_gates(Phase.INTAKE, [
        Gate("intent classified"),
        Gate("complexity assessed"),
    ])
    state.set_gates(Phase.SPECIFY, [
        Gate("acceptance criteria written"),
        Gate("affected files listed"),
    ])
    state.set_gates(Phase.PLAN, [
        Gate("every chapter has affected files and verification"),
    ])
    state.set_gates(Phase.CRITIQUE, [
        Gate("critique produced with CONFIRMED or UNVERIFIED findings"),
    ])
    state.set_gates(Phase.APPROVE, [
        Gate("user approved the plan"),
    ])
    state.set_gates(Phase.IMPLEMENT, [
        Gate("tests written where a suite exists"),
        Gate("build or type check run"),
    ])
    state.set_gates(Phase.REVIEW, [
        Gate("independent review completed"),
    ])
    state.set_gates(Phase.VERIFY, [
        Gate("every acceptance criterion checked against evidence"),
    ])
    state.approval_required = tier in (Workflow.PLANNED, Workflow.FULL)
    return state
