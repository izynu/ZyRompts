"""Prompt engineering: scoring, rewriting, templates, and framework selection.

This is the Prompt Master layer distilled into deterministic code plus
structured data. The scoring function gives an objective quality number so the
improver can prove a rewrite is better, and the templates are the CO-STAR /
RTF / RISEN / CRISPE / few-shot frameworks as data, not prose.

Design rules:
- Scoring is deterministic and explainable: every point is attributed.
- Rewriting is conservative: it adds structure and evidence, it never invents
  requirements the user did not state.
- Model-aware optimization routes on capability class, never on hardcoded
  version strings that rot.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from .classify import Classification, Intent, OutputShape, classify


class Framework(str, Enum):
    RTF = "RTF"          # Role, Task, Format
    COSTAR = "CO-STAR"   # Context, Objective, Style, Tone, Audience, Response
    RISEN = "RISEN"      # Role, Instructions, Steps, End goal, Narrowing
    CRISPE = "CRISPE"    # Capacity, Role, Insight, Statement, Personality, Experiment
    FEW_SHOT = "Few-Shot"


class ModelFamily(str, Enum):
    """Capability classes, not version strings. Version strings rot."""

    CLAUDE = "claude"
    OPENAI_REASONING = "openai-reasoning"
    OPENAI_CHAT = "openai-chat"
    GEMINI = "gemini"
    LOCAL = "local"
    UNKNOWN = "unknown"


@dataclass
class ScoreBreakdown:
    total: int
    max_total: int
    components: dict[str, int] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    not_applicable: list[str] = field(default_factory=list)

    @property
    def grade(self) -> str:
        ratio = self.total / self.max_total if self.max_total else 0
        if ratio >= 0.85:
            return "A"
        if ratio >= 0.7:
            return "B"
        if ratio >= 0.5:
            return "C"
        if ratio >= 0.3:
            return "D"
        return "F"

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "max_total": self.max_total,
            "grade": self.grade,
            "components": dict(self.components),
            "missing": list(self.missing),
            "not_applicable": list(self.not_applicable),
        }


# Component -> (weight, human label)
_WEIGHTS = {
    "task_clarity": 20,
    "target_context": 15,
    "output_format": 15,
    "constraints": 15,
    "success_criteria": 15,
    "scope_boundaries": 10,
    "examples": 10,
}

_PRECISE_VERB = re.compile(
    r"\b(refactor|rename|migrate|extract|replace|convert|implement|add|remove|"
    r"delete|move|optimi[sz]e|reduce|increase|document|test|fix|debug|trace|"
    r"measure|benchmark|validate|generate|write|update|pin|upgrade|downgrade|"
    # "make X accept Y" and "have X return Y" are precise operations written
    # with a light verb. Without these, a well-specified request scores as if
    # it were vague.
    r"accept|return|print|parse|sort|emit|raise|reject|allow|deny|expose|"
    r"require|support|handle|send|read|load|save|store|compute|"
    # Question verbs are precise operations too, for the intent they belong to.
    r"explain|describe|compare|summarize|clarify|outline|list)\b", re.I)
_VAGUE_VERB = re.compile(
    r"\b(improve|enhance|make (it )?better|fix up|clean ?up|sort out|look at|"
    r"deal with|handle|address|touch up|polish)\b", re.I)
_TARGET = re.compile(
    r"(\.{0,2}/[\w./-]+|[\w-]+\.\w{1,5}\b|`[^`]+`|#[0-9]+|"
    r"\b[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*\b|\b\w+\(\))")
_FORMAT = re.compile(
    r"\b(json|yaml|markdown|table|bullet|prose|diff|patch|csv|xml|html|"
    r"paragraph|sentences?|words?|lines?|list|outline|code block)\b", re.I)
_CONSTRAINT = re.compile(
    r"\b(must|must not|never|always|only|without|do not|don'?t|required|"
    r"forbidden|limit|at most|no more than|at least|constraint)\b", re.I)
_SUCCESS = re.compile(
    r"\b(acceptance criteria|done when|definition of done|expected (output|result)|"
    r"should (return|print|pass|fail)|verify that|tests? (pass|fail)|"
    r"success (means|criteria)|assert)\b", re.I)
_SCOPE = re.compile(
    r"\b(only (in|within|touch)|do not (touch|modify|change)|outside scope|"
    r"scope:|in scope|out of scope|files?:|directory|module|package)\b", re.I)
_EXAMPLE = re.compile(r"(example|e\.g\.|for instance|input:|output:)", re.I)


def score_prompt(prompt: str) -> ScoreBreakdown:
    """Score 0..100 across seven weighted dimensions.

    Every component is independently attributable, so the improver can point at
    exactly what is missing instead of saying "be more specific".
    """
    text = prompt if isinstance(prompt, str) else ""
    components: dict[str, int] = {}
    missing: list[str] = []

    # Task clarity: a precise verb plus a concrete target.
    precise = bool(_PRECISE_VERB.search(text))
    vague = bool(_VAGUE_VERB.search(text))
    if precise and not vague:
        components["task_clarity"] = _WEIGHTS["task_clarity"]
    elif precise:
        components["task_clarity"] = int(_WEIGHTS["task_clarity"] * 0.6)
    elif vague:
        components["task_clarity"] = int(_WEIGHTS["task_clarity"] * 0.2)
        missing.append("replace the vague verb with a precise operation")
    else:
        components["task_clarity"] = 0
        missing.append("state the precise action to perform")

    if _TARGET.search(text):
        components["target_context"] = _WEIGHTS["target_context"]
    else:
        components["target_context"] = 0
        missing.append("name the file, symbol, error, or source the task applies to")

    if _FORMAT.search(text):
        components["output_format"] = _WEIGHTS["output_format"]
    else:
        components["output_format"] = 0
        missing.append("specify the output format and length")

    if _CONSTRAINT.search(text):
        components["constraints"] = _WEIGHTS["constraints"]
    else:
        components["constraints"] = 0
        missing.append("state what must and must not happen")

    if _SUCCESS.search(text):
        components["success_criteria"] = _WEIGHTS["success_criteria"]
    else:
        components["success_criteria"] = 0
        missing.append("add a checkable success criterion (done when ...)")

    if _SCOPE.search(text):
        components["scope_boundaries"] = _WEIGHTS["scope_boundaries"]
    else:
        components["scope_boundaries"] = 0
        missing.append("bound the scope: which files or modules may change")

    if _EXAMPLE.search(text):
        components["examples"] = _WEIGHTS["examples"]
    else:
        components["examples"] = 0

    # A question has no acceptance criteria and no scope boundary to declare, so
    # grading it against them scores a perfectly clear request as an F. Mark
    # those dimensions not-applicable and shrink the denominator to match: the
    # score answers "is this prompt clear for what it is trying to do", not "did
    # it fill every slot in a coding template".
    not_applicable: list[str] = []
    if classify(text).intent in (Intent.EXPLAIN, Intent.QUESTION):
        for key in ("success_criteria", "scope_boundaries"):
            components.pop(key, None)
        missing = [m for m in missing
                   if "success criterion" not in m and "bound the scope" not in m]
        not_applicable.extend(["success_criteria", "scope_boundaries"])

    max_total = sum(_WEIGHTS[key] for key in components)
    total = sum(components.values())
    return ScoreBreakdown(total=total, max_total=max_total,
                          components=components, missing=missing,
                          not_applicable=not_applicable)


def choose_framework(classification: Classification, prompt: str) -> Framework:
    """Pick the lightest framework that fits the task shape."""
    if classification.output_shape is OutputShape.JSON or _EXAMPLE.search(prompt):
        return Framework.FEW_SHOT
    if classification.complexity.value in ("large", "epic"):
        return Framework.RISEN
    if classification.intent in (Intent.BUILD, Intent.REFACTOR):
        return Framework.COSTAR
    if classification.intent in (Intent.EXPLAIN, Intent.QUESTION, Intent.FIX):
        return Framework.RTF
    return Framework.COSTAR


_TEMPLATES: dict[Framework, list[tuple[str, str]]] = {
    Framework.RTF: [
        ("Role", "You are a {role}."),
        ("Task", "{task}"),
        ("Format", "{format}"),
    ],
    Framework.COSTAR: [
        ("Context", "{context}"),
        ("Objective", "{task}"),
        ("Style", "{style}"),
        ("Tone", "Direct and technical."),
        ("Audience", "{audience}"),
        ("Response", "{format}"),
    ],
    Framework.RISEN: [
        ("Role", "You are a {role}."),
        ("Instructions", "{task}"),
        ("Steps", "1. {step1}\n2. {step2}"),
        ("End goal", "{goal}"),
        ("Narrowing", "Do only this. Do not add features beyond the stated goal."),
    ],
    Framework.CRISPE: [
        ("Capacity", "You are a {role} with deep expertise in this domain."),
        ("Role", "{role}"),
        ("Insight", "{context}"),
        ("Statement", "{task}"),
        ("Personality", "Direct, evidence-driven, terse."),
        ("Experiment", "Produce the result; state assumptions you had to make."),
    ],
    Framework.FEW_SHOT: [
        ("Task", "{task}"),
        ("Format", "{format}"),
        ("Examples", "Input: {example_in}\nOutput: {example_out}"),
    ],
}


def _role_for(classification: Classification) -> str:
    mapping = {
        "frontend": "senior frontend engineer",
        "backend": "senior backend engineer",
        "database": "database engineer",
        "infra": "platform and infrastructure engineer",
        "security": "application security engineer",
        "data": "data engineer",
        "ml": "machine learning engineer",
        "mobile": "mobile engineer",
        "docs": "technical writer",
    }
    for domain in classification.domains:
        if domain in mapping:
            return mapping[domain]
    return "senior software engineer"


@dataclass
class ImprovedPrompt:
    original: str
    improved: str
    framework: Framework
    before: ScoreBreakdown
    after: ScoreBreakdown
    changes: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)

    @property
    def delta(self) -> int:
        return self.after.total - self.before.total

    def to_dict(self) -> dict:
        return {
            "framework": self.framework.value,
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
            "delta": self.delta,
            "changes": list(self.changes),
            "open_questions": list(self.open_questions),
            "improved": self.improved,
        }


def improve_prompt(prompt: str, framework: Framework | None = None) -> ImprovedPrompt:
    """Rewrite a prompt into a structured, higher-scoring prompt.

    The rewrite never invents domain facts. It re-frames the user's own words
    into an explicit contract and marks every gap as an open question the user
    must answer, rather than silently guessing.
    """
    original = prompt if isinstance(prompt, str) else ""
    classification = classify(original)
    framework = framework or choose_framework(classification, original)
    before = score_prompt(original)

    task = " ".join(original.split())
    role = _role_for(classification)
    fmt = (classification.output_shape.value
           if classification.output_shape is not OutputShape.UNSPECIFIED
           else "concise, structured, with a short rationale")
    context = ("Project context: " + ", ".join(classification.domains)
               if classification.domains else "Project context: [add stack and constraints]")

    slots = {
        "role": role, "task": task, "format": fmt, "context": context,
        "style": "Precise, terse, no filler.", "audience": "The engineer who will act on it.",
        "goal": "[state the end state that means the task is done]",
        "step1": "[first concrete action]", "step2": "[second concrete action]",
        "example_in": "[representative input]", "example_out": "[expected output]",
    }

    lines = [f"# {framework.value} prompt", ""]
    for label, template in _TEMPLATES[framework]:
        rendered = template.format(**slots)
        lines.append(f"## {label}")
        lines.append(rendered)
        lines.append("")

    lines.append("## Constraints")
    lines.append("- Do only what is asked. Do not add features, refactors, or abstractions beyond the task.")
    lines.append("- If a requirement is ambiguous, ask before building.")
    lines.append("- Distinguish verified facts from assumptions in the final report.")
    lines.append("")

    changes: list[str] = []
    if before.components.get("task_clarity", 0) < _WEIGHTS["task_clarity"]:
        changes.append("rewrote the task as a precise operation")
    if not before.components.get("target_context"):
        changes.append("added an explicit target slot")
    if not before.components.get("output_format"):
        changes.append(f"locked the output format to {fmt}")
    if not before.components.get("success_criteria"):
        changes.append("added a done-when placeholder")
    if not before.components.get("constraints"):
        changes.append("added a constraints block")
    if not before.components.get("scope_boundaries"):
        changes.append("added scope discipline")

    improved = "\n".join(lines).rstrip() + "\n"
    after = score_prompt(improved)

    return ImprovedPrompt(
        original=original,
        improved=improved,
        framework=framework,
        before=before,
        after=after,
        changes=changes,
        open_questions=before.missing,
    )


_MODEL_NOTES: dict[ModelFamily, list[str]] = {
    ModelFamily.CLAUDE: [
        "Be direct; state the desired output, constraints and scope explicitly.",
        "Use XML tags (<context>, <task>, <constraints>, <output_format>) for complex prompts.",
        "Put long source documents before the query, wrapped in descriptive tags.",
        "Ask for conclusions and evidence, never for hidden reasoning.",
        "Prefer positive instructions describing the desired result over long prohibition lists.",
    ],
    ModelFamily.OPENAI_REASONING: [
        "Short, clean instructions only. These models reason internally.",
        "Never add chain-of-thought or 'think step by step' scaffolding; it degrades output.",
        "Prefer zero-shot first; add few-shot only if strictly needed.",
        "State what you want and what done looks like. Nothing more.",
    ],
    ModelFamily.OPENAI_CHAT: [
        "Structure as Goal, Context, Scope, Constraints, Approval boundaries, Done.",
        "Use explicit format locks and 2-5 examples when format matters.",
        "Keep runtime settings out of the prompt text.",
    ],
    ModelFamily.GEMINI: [
        "Leverage the large context window; put documents first.",
        "Add a citation guard: cite only sources you are certain of, else say [uncertain].",
        "Lock output formats with a labelled example; this family can drift.",
    ],
    ModelFamily.LOCAL: [
        "Shorter, flatter prompts outperform nested ones; local models lose coherence.",
        "Always include a role in the system prompt.",
        "Be more explicit than with hosted frontier models.",
    ],
    ModelFamily.UNKNOWN: [
        "Verify the model's current capabilities before relying on version-specific behavior.",
        "Use a durable structure: goal, context, constraints, output contract, done.",
    ],
}


def model_notes(family: ModelFamily | str) -> list[str]:
    """Return durable prompting guidance for a model family (never version-specific)."""
    if isinstance(family, str):
        try:
            family = ModelFamily(family.lower())
        except ValueError:
            family = ModelFamily.UNKNOWN
    return list(_MODEL_NOTES.get(family, _MODEL_NOTES[ModelFamily.UNKNOWN]))


def detect_model_family(text: str) -> ModelFamily:
    """Infer the target model family from a prompt or config string."""
    lowered = (text or "").lower()
    if any(k in lowered for k in ("claude", "anthropic", "opus", "sonnet", "haiku", "fable")):
        return ModelFamily.CLAUDE
    if any(k in lowered for k in ("o3", "o4", "reasoning", "gpt-5", "gpt-6", "codex")):
        return ModelFamily.OPENAI_REASONING
    if any(k in lowered for k in ("gpt-4", "chatgpt", "openai")):
        return ModelFamily.OPENAI_CHAT
    if any(k in lowered for k in ("gemini", "google ai", "vertex")):
        return ModelFamily.GEMINI
    if any(k in lowered for k in ("ollama", "llama", "mistral", "qwen", "local")):
        return ModelFamily.LOCAL
    return ModelFamily.UNKNOWN
