"""ZyRompts: a modular multi-agent workflow framework for AI coding agents.

The package is deliberately dependency-free so it can run inside a hook, a CI
job, or an air-gapped machine with nothing but a Python 3.9+ interpreter.

Public surface:
    classify(prompt)          -> Classification
    improve_prompt(prompt)    -> ImprovedPrompt
    score_prompt(prompt)      -> ScoreBreakdown
    evaluate(tool, args)      -> Verdict
    run_event(event, payload) -> str
"""

from __future__ import annotations

__version__ = "0.1.0"

from .classify import (  # noqa: E402
    Classification,
    Complexity,
    Intent,
    OutputShape,
    Priority,
    Signal,
    Workflow,
    classify,
)
from .decorum import DECORUM, check_reply  # noqa: E402
from .policy import Autonomy, Decision, PolicyConfig, Verdict, evaluate, redact_secrets  # noqa: E402
from .prompts import (  # noqa: E402
    Framework,
    ImprovedPrompt,
    ModelFamily,
    ScoreBreakdown,
    detect_model_family,
    improve_prompt,
    model_notes,
    score_prompt,
)
from .review import (  # noqa: E402
    Confidence,
    ReviewReport,
    Severity,
    critique_diff,
    critique_plan,
)
from .research import Finding, ResearchReport, SourceTier, classify_source  # noqa: E402
from .state import ProjectState, StateStore, Task  # noqa: E402
from .workflow import Phase, WorkflowState, start  # noqa: E402

__all__ = [
    "__version__",
    "Classification", "Complexity", "Intent", "OutputShape", "Priority", "Signal",
    "Workflow", "classify",
    "DECORUM", "check_reply",
    "Autonomy", "Decision", "PolicyConfig", "Verdict", "evaluate", "redact_secrets",
    "Framework", "ImprovedPrompt", "ModelFamily", "ScoreBreakdown",
    "detect_model_family", "improve_prompt", "model_notes", "score_prompt",
    "Confidence", "ReviewReport", "Severity", "critique_diff", "critique_plan",
    "Finding", "ResearchReport", "SourceTier", "classify_source",
    "ProjectState", "StateStore", "Task",
    "Phase", "WorkflowState", "start",
]
