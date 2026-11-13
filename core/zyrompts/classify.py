"""Deterministic prompt classification.

This module is the intake brain of the framework. It reads a raw user prompt
and returns a structured `Classification` without calling a model: intent,
complexity, domains, risk flags, ambiguity, output shape, priority and a
recommended workflow. Everything here is pure and testable, so the expensive
model-side judgement (does this prompt *really* need clarification?) stays a
cheap, deterministic pre-filter.

Design rules:
- Pure functions, no I/O, no environment access.
- Every signal carries evidence so a reviewer can refute it.
- Under-detect rather than over-detect: a missed signal costs a correction
  round-trip, a false one costs a wrong workflow, which is worse.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Intent(str, Enum):
    BUILD = "build"
    FIX = "fix"
    REFACTOR = "refactor"
    EXPLAIN = "explain"
    RESEARCH = "research"
    REVIEW = "review"
    PLAN = "plan"
    PROMPT_ENGINEERING = "prompt-engineering"
    OPS = "ops"
    QUESTION = "question"
    UNKNOWN = "unknown"


class Complexity(str, Enum):
    TRIVIAL = "trivial"
    SMALL = "small"
    MODERATE = "moderate"
    LARGE = "large"
    EPIC = "epic"

    @property
    def rank(self) -> int:
        return _COMPLEXITY_RANK[self]

    def at_least(self, other: "Complexity") -> bool:
        """Ordering helper.

        These enums subclass str, so `a >= b` compares the *labels*
        ("trivial" > "moderate") and silently gives the wrong answer. Every
        ordering decision must go through rank, never through the enum itself.
        """
        return self.rank >= other.rank


_COMPLEXITY_RANK = {
    Complexity.TRIVIAL: 0,
    Complexity.SMALL: 1,
    Complexity.MODERATE: 2,
    Complexity.LARGE: 3,
    Complexity.EPIC: 4,
}


class Priority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class OutputShape(str, Enum):
    CODE = "code"
    PROSE = "prose"
    TABLE = "table"
    JSON = "json"
    DIFF = "diff"
    PLAN = "plan"
    UNSPECIFIED = "unspecified"


class Workflow(str, Enum):
    """Workflow tiers. Cheap by default; the full lifecycle is opt-in by evidence."""

    DIRECT = "direct"          # answer or one-step edit
    LIGHT = "light"            # classify -> act -> verify
    PLANNED = "planned"        # spec -> plan -> critique -> approve -> execute
    FULL = "full"              # the complete 24-step lifecycle


@dataclass(frozen=True)
class Signal:
    """One detected property of the prompt, with the evidence that produced it."""

    dimension: str
    value: str
    confidence: float
    evidence: str

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "value": self.value,
            "confidence": round(self.confidence, 2),
            "evidence": self.evidence,
        }


@dataclass
class Classification:
    intent: Intent
    complexity: Complexity
    priority: Priority
    output_shape: OutputShape
    workflow: Workflow
    domains: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    word_count: int = 0

    @property
    def is_ambiguous(self) -> bool:
        return "ambiguous" in self.flags

    @property
    def needs_research(self) -> bool:
        return "needs_research" in self.flags

    @property
    def injection_suspected(self) -> bool:
        return "injection_suspected" in self.flags

    def to_dict(self) -> dict:
        return {
            "intent": self.intent.value,
            "complexity": self.complexity.value,
            "priority": self.priority.value,
            "output_shape": self.output_shape.value,
            "workflow": self.workflow.value,
            "domains": list(self.domains),
            "flags": list(self.flags),
            "ambiguities": list(self.ambiguities),
            "word_count": self.word_count,
            "scores": {k: round(v, 2) for k, v in self.scores.items()},
            "signals": [s.to_dict() for s in self.signals],
        }


# --- cue tables -------------------------------------------------------------
# Ordered by specificity: the first matching group wins for intent.

_INTENT_CUES: list[tuple[Intent, str, re.Pattern[str]]] = [
    (Intent.PROMPT_ENGINEERING, "prompt-engineering",
     re.compile(r"\b(prompt|system message|few[- ]shot|co-?star|risen|cispre|rtf)\b", re.I)),
    (Intent.REVIEW, "review",
     re.compile(r"\b(review|audit|critique|lint|code[- ]review|security (check|audit)|"
                r"check for (bugs|vulns|vulnerabilities))\b", re.I)),
    (Intent.RESEARCH, "research",
     re.compile(r"\b(research|investigate|find out|compare|survey|look up|"
                r"what do (the )?docs say|best practice|state of the art)\b", re.I)),
    (Intent.PLAN, "plan",
     re.compile(r"\b(plan|roadmap|design doc|spec(ification)?|architecture proposal|"
                r"break (this|it) down)\b", re.I)),
    (Intent.REFACTOR, "refactor",
     re.compile(r"\b(refactor|restructure|clean ?up|rewrite|moderni[sz]e|"
                r"extract (a )?(class|function|module)|split .* into)\b", re.I)),
    (Intent.FIX, "fix",
     re.compile(r"\b(fix|bug|broken|fails?|failing|error|crash|regression|"
                r"traceback|exception|stack ?trace|doesn'?t work|not working)\b", re.I)),
    # A reported symptom with no verb is still a fix request: "the login endpoint
    # returns 500 when the email has a plus sign" names a defect, not a task.
    (Intent.FIX, "symptom",
     re.compile(r"\b(returns?|throws?|gives?|shows?|emits?)\b.{0,24}"
                r"\b(\d{3}|error|exception|wrong|empty|null|undefined|nan)\b", re.I)),
    (Intent.BUILD, "build",
     re.compile(r"\b(add|build|create|implement|make|write|generate|scaffold|"
                r"set ?up|integrate|migrate|port|support)\b", re.I)),
    (Intent.OPS, "ops",
     re.compile(r"\b(deploy|release|ci\b|cd\b|pipeline|docker|kubernetes|terraform|"
                r"ansible|systemd|nginx|server|backup|restore|rotate)\b", re.I)),
    (Intent.EXPLAIN, "explain",
     re.compile(r"\b(explain|why|how does|how do|what is|what does|what are|"
                r"walk me through|understand|difference between|meaning of)\b", re.I)),
]

# An interrogative opener asks for an answer, so it outranks the verb table:
# "why does the build fail" is a diagnosis request, not an instruction to patch.
# The exception is "how do I <action verb>", which asks for the work to be done.
# Only genuine question openers are listed. "do" is deliberately excluded: "do a
# security review" is imperative, and treating it as a question loses the intent.
_WH_OPENER = re.compile(r"^\s*(why|what|how|which|who|whose|when|where)\b", re.I)
_AUX_OPENER = re.compile(r"^\s*(is|are|was|were|does|did|can|could|should|would|will)\b", re.I)
_HOW_TO_ACT = re.compile(
    r"^\s*how\s+(?:do\s+i|to|can\s+i|should\s+i|would\s+i)\s+"
    r"(add|build|create|implement|make|write|generate|fix|refactor|migrate|"
    r"deploy|install|set\s?up|configure|optimize)\b", re.I)
# Inside a wh-question, these cues mean "explain it to me" rather than "answer
# this open question". Kept separate from _INTENT_CUES so the ordering of that
# table is not disturbed.
_EXPLAIN_ONLY = re.compile(
    r"\b(explain|meaning of|difference between|walk me through|"
    r"what (is|are|does)|how does|how do)\b", re.I)

# Intents that change code. With no concrete anchor these are underspecified.
_CODE_CHANGING = frozenset({Intent.BUILD, Intent.FIX, Intent.REFACTOR, Intent.OPS})

# Complexity reasons that indicate genuinely wide scope. A short prompt carrying
# one of these is terse, not trivial.
_WIDE_SCOPE_REASONS = frozenset({
    "architectural or cross-cutting change",
    "wide-touching rewrite",
    "explicitly wide scope",
})

# Words that scale the complexity score. Each entry is (pattern, weight, reason).
_COMPLEXITY_CUES: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"\b(architect|architecture|design (system|pattern)|migration|"
                r"migrate)\b", re.I),
     3.0, "architectural or cross-cutting change"),
    # Named architectural scope, weighted separately from the migration verb.
    # "migrate the monolith to microservices" names three concerns; letting the
    # pattern above fire once for all of them scores it as a routine migration.
    (re.compile(r"\b(multi[- ]?(tenant|service|module|agent)|distributed|"
                r"monolith|micro[- ]?services?)\b", re.I),
     1.5, "named architectural scope"),
    (re.compile(r"\b(refactor|rewrite|redesign|restructure)\b", re.I),
     2.0, "wide-touching rewrite"),
    (re.compile(r"\b(across|throughout|everywhere|all (files|modules|services|packages)|"
                r"entire (codebase|repo|project|app))\b", re.I),
     2.5, "explicitly wide scope"),
    (re.compile(r"\b(frontend|backend|full[- ]?stack|database|api|auth|deploy|ci)\b", re.I),
     0.5, "multiple technical layers named"),
    (re.compile(r"\b(and then|after that|followed by|step by step|multi[- ]step|"
                r"end[- ]to[- ]end)\b", re.I),
     1.5, "multi-step phrasing"),
    (re.compile(r"\b(tests?|coverage|benchmark|perf(ormance)?)\b", re.I),
     0.75, "verification work implied"),
    (re.compile(r"\b(security|auth|permission|credential|secret|payment|pii)\b", re.I),
     1.0, "security-sensitive surface"),
    (re.compile(r"\b(production|prod|live|users|customers|real data)\b", re.I),
     1.0, "production impact"),
]

_DOMAIN_CUES: dict[str, re.Pattern[str]] = {
    "frontend": re.compile(r"\b(react|vue|svelte|angular|css|tailwind|ui|ux|component|"
                           r"browser|dom|html|frontend|next\.?js)\b", re.I),
    "backend": re.compile(r"\b(api|server|endpoint|django|flask|fastapi|express|"
                          r"spring|rails|laravel|graphql|rest|backend|microservice)\b", re.I),
    "database": re.compile(r"\b(sql|postgres|mysql|sqlite|mongo|redis|schema|migration|"
                           r"index|query plan|orm|prisma|drizzle)\b", re.I),
    "infra": re.compile(r"\b(docker|kubernetes|k8s|terraform|ansible|ci|cd|pipeline|"
                        r"aws|gcp|azure|nginx|systemd|deploy|helm)\b", re.I),
    "security": re.compile(r"\b(security|vulnerab|exploit|xss|csrf|sqli|injection|"
                           r"auth(n|z)?|oauth|jwt|secret|credential|pentest)\b", re.I),
    "data": re.compile(r"\b(pandas|numpy|etl|warehouse|spark|airflow|dataset|"
                       r"analytics|csv|parquet)\b", re.I),
    "ml": re.compile(r"\b(model|training|inference|embedding|llm|transformer|"
                     r"pytorch|tensorflow|fine[- ]?tun)\b", re.I),
    "mobile": re.compile(r"\b(ios|android|swift|kotlin|flutter|react native|"
                         r"mobile app|app store)\b", re.I),
    "docs": re.compile(r"\b(readme|docs?|documentation|changelog|guide|"
                       r"tutorial|comment)\b", re.I),
}

_OUTPUT_CUES: list[tuple[OutputShape, re.Pattern[str]]] = [
    (OutputShape.JSON, re.compile(r"\b(json|yaml|yml|schema|structured output)\b", re.I)),
    (OutputShape.TABLE, re.compile(r"\b(table|matrix|comparison table|spreadsheet)\b", re.I)),
    (OutputShape.DIFF, re.compile(r"\b(diff|patch|pull request|pr\b|commit)\b", re.I)),
    (OutputShape.PLAN, re.compile(r"\b(plan|checklist|roadmap|steps)\b", re.I)),
    (OutputShape.CODE, re.compile(r"\b(code|function|class|module|implement|script|"
                                  r"test|file)\b", re.I)),
    (OutputShape.PROSE, re.compile(r"\b(explain|summary|report|write|essay|"
                                   r"describe|document)\b", re.I)),
]

_URGENT = re.compile(r"\b(urgent|asap|immediately|right now|critical|prod is down|"
                     r"outage|hotfix|sev ?[12])\b", re.I)
_HIGH = re.compile(r"\b(important|soon|today|blocking|blocker|priority)\b", re.I)

# Vague prompts: a verb with no object, or a pronoun-only reference.
_VAGUE_VERB = re.compile(
    r"^\s*(please\s+)?(fix|update|change|improve|check|look at|handle|clean|"
    r"sort|do|make it|help|continue|finish|debug)\b", re.I)
_PRONOUN_ONLY = re.compile(r"\b(it|this|that|these|those|the thing|stuff)\b", re.I)
# An anchor is something concrete the task can attach to: a path, a filename,
# a backticked symbol, an issue number, or a CamelCase/snake_case identifier.
# These patterns stay case-sensitive on purpose: under IGNORECASE, `[A-Z]`
# matches any letter, so "fix" would register as a CamelCase identifier and
# every vague prompt would pass the check.
_ANCHOR_PATH = re.compile(r"(?:\.{0,2}/)[\w.-]+(?:/[\w.-]+)*")
_ANCHOR_FILE = re.compile(
    r"\b[\w-]+\.(?:py|js|ts|tsx|jsx|go|rs|java|rb|php|cs|cpp|c|h|md|json|ya?ml|toml|sql|sh)\b")
_ANCHOR_CODE = re.compile(r"`[^`]+`|#[0-9]+")
_ANCHOR_IDENT = re.compile(
    r"\b[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*\b"          # CamelCase
    r"|\b[a-z][a-z0-9]*_[a-z0-9_]+\b"                # snake_case
    r"|\b[a-z]+[A-Z][A-Za-z0-9]*\b")                 # camelCase
_ANCHORS = (_ANCHOR_PATH, _ANCHOR_FILE, _ANCHOR_CODE, _ANCHOR_IDENT)
_ACCEPTANCE = re.compile(
    r"\b(acceptance criteria|done when|definition of done|should return|expected output|"
    r"must pass|tests? (pass|fail)|verify that|assert)\b", re.I)

# Prompt-injection shapes. These are signals, never a verdict: the policy layer
# makes the actual decision, and content from tool output is untrusted anyway.
_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("instruction_override",
     re.compile(r"\b(ignore|disregard|forget)\b.{0,40}\b(previous|prior|above|earlier|"
                r"all)\b.{0,20}\b(instruction|prompt|rule|direction)", re.I)),
    ("role_hijack",
     re.compile(r"\b(you are now|from now on you|pretend (to be|you are)|"
                r"new (system )?(prompt|instructions?))\b", re.I)),
    ("prompt_exfiltration",
     re.compile(r"\b(reveal|show|print|repeat|output)\b.{0,30}\b(system prompt|"
                r"your instructions|initial prompt|hidden rules?)\b", re.I)),
    ("safety_bypass",
     re.compile(r"\b(jailbreak|DAN mode|developer mode enabled|bypass (your )?"
                r"(safety|filter|guardrail|restriction))\b", re.I)),
    ("encoded_payload",
     re.compile(r"[A-Za-z0-9+/]{120,}={0,2}", re.I)),
]

# Destructive operations: raise the risk tier, never block by themselves.
_DESTRUCTIVE = re.compile(
    r"\b(rm\s+-rf|drop\s+(table|database)|truncate\s+table|delete\s+(all|every)|"
    r"force[- ]push|git reset --hard|overwrite|wipe|purge|destroy|"
    r"chmod\s+777|sudo\s+rm)\b", re.I)

_HARNESS_TAG = re.compile(
    r"^\s*<(task-notification|system-reminder|command-name|command-message|"
    r"local-command-(stdout|stderr|caveat)|user-prompt-submit-hook)")


def _words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _first_intent(text: str) -> tuple[Intent, Signal | None]:
    # The verb table is ordered, so it must not decide a question. Ask "why does
    # the build fail" and the FIX cue matches "fail", which would turn a
    # diagnosis request into a patch instruction.
    #
    # A wh-opener is a question unless it is "how do I <action>". But "what is a
    # monad" and "what is the auth middleware doing" are explanations, not open
    # questions, so the EXPLAIN table still gets a vote there. An auxiliary
    # opener ("why does it fail" -> auxiliary, "is the cache warm") is a question
    # outright.
    if _WH_OPENER.match(text) and not _HOW_TO_ACT.match(text):
        explain = _EXPLAIN_ONLY.search(text)
        if explain:
            return Intent.EXPLAIN, Signal("intent", Intent.EXPLAIN.value, 0.75,
                                          f"wh-opener with explain cue {explain.group(0)!r}")
        return Intent.QUESTION, Signal("intent", Intent.QUESTION.value, 0.75,
                                       "wh-opener")
    if _AUX_OPENER.match(text):
        return Intent.QUESTION, Signal("intent", Intent.QUESTION.value, 0.75,
                                       "auxiliary opener")
    for intent, label, pattern in _INTENT_CUES:
        match = pattern.search(text)
        if match:
            return intent, Signal("intent", intent.value, 0.7,
                                  f"matched {label!r}: {match.group(0)!r}")
    return Intent.UNKNOWN, None


def detect_injection(text: str) -> list[Signal]:
    """Return one signal per injection shape found. Never raises."""
    found = []
    for name, pattern in _INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            snippet = match.group(0)[:60]
            found.append(Signal("injection", name, 0.6, f"{name}: {snippet!r}"))
    return found


def complexity_score(text: str) -> tuple[float, list[Signal]]:
    """Score 0..10 and return the cues that produced it."""
    score = 0.0
    signals: list[Signal] = []
    for pattern, weight, reason in _COMPLEXITY_CUES:
        match = pattern.search(text)
        if match:
            score += weight
            signals.append(Signal("complexity", reason, 0.6, f"cue {match.group(0)!r}"))
    words = _words(text)
    if words > 120:
        score += 1.0
        signals.append(Signal("complexity", "long prompt", 0.5, f"{words} words"))
    if words > 350:
        score += 1.0
        signals.append(Signal("complexity", "very long prompt", 0.5, f"{words} words"))
    # A single-sentence ask stays cheap even if a cue fired, but only when the
    # cue was weak. Terse users are common: "refactor the payment module into
    # separate services" is seven words and a large change. Clamping that to
    # `small` routes real work down the cheapest path, so the clamp is a floor
    # on weak evidence, not a cap on strong evidence.
    if words <= 8 and len(re.findall(r"[.!?]", text)) <= 1:
        strong = any(s.value in _WIDE_SCOPE_REASONS for s in signals)
        if not strong:
            score = min(score, 1.5)
            signals.append(Signal("complexity", "one-line ask", 0.6, f"{words} words"))
        else:
            signals.append(Signal("complexity", "terse but wide scope", 0.7,
                                  f"{words} words, wide-scope cue retained"))
    return score, signals


def _bucket(score: float) -> Complexity:
    if score < 1.0:
        return Complexity.TRIVIAL
    if score < 2.5:
        return Complexity.SMALL
    if score < 4.5:
        return Complexity.MODERATE
    if score < 7.0:
        return Complexity.LARGE
    return Complexity.EPIC


def has_anchor(text: str) -> bool:
    """True when the prompt names something concrete to act on."""
    return any(pattern.search(text) for pattern in _ANCHORS)


def ambiguity_findings(text: str) -> list[str]:
    """Return human-readable ambiguity reasons (empty when the prompt is clear)."""
    reasons: list[str] = []
    words = _words(text)
    anchored = has_anchor(text)

    if words == 0:
        return ["empty prompt"]
    if words <= 4 and not anchored:
        reasons.append("very short with no concrete target")
    elif _VAGUE_VERB.match(text) and not anchored:
        reasons.append("vague verb with no file, symbol, or error named")
    elif _PRONOUN_ONLY.search(text) and not anchored and words < 25:
        reasons.append("refers to 'it/this' without naming the target")

    if not _ACCEPTANCE.search(text) and _bucket(complexity_score(text)[0]).at_least(Complexity.MODERATE):
        reasons.append("no acceptance criteria stated for a non-trivial change")
    return reasons


def contradictory(text: str) -> list[str]:
    """Detect a small set of mutually exclusive requirement pairs.

    Deliberately conservative: a false contradiction accusation is worse than a
    missed one, so each pair must appear as explicit requirement language.
    """
    pairs = [
        ("keep backward compatibility", "breaking change"),
        ("backward compatible", "rewrite"),
        ("no new dependencies", "add a library"),
        ("do not modify tests", "update the tests"),
        ("zero downtime", "drop the table"),
        ("must be fast", "exhaustive verification"),
        ("keep the api stable", "rename the endpoint"),
    ]
    lowered = text.lower()
    return [f"{a!r} conflicts with {b!r}" for a, b in pairs if a in lowered and b in lowered]


def detect_priority(text: str) -> Priority:
    if _URGENT.search(text):
        return Priority.URGENT
    if _HIGH.search(text):
        return Priority.HIGH
    return Priority.NORMAL


def detect_output(text: str) -> OutputShape:
    for shape, pattern in _OUTPUT_CUES:
        if pattern.search(text):
            return shape
    return OutputShape.UNSPECIFIED


def detect_domains(text: str) -> list[str]:
    return [name for name, pattern in _DOMAIN_CUES.items() if pattern.search(text)]


def choose_workflow(intent: Intent, complexity: Complexity, flags: list[str],
                    has_target: bool = True) -> Workflow:
    """Map classification to the cheapest workflow that can still be correct."""
    if "injection_suspected" in flags:
        return Workflow.LIGHT
    if intent in (Intent.EXPLAIN, Intent.QUESTION):
        tier = (Workflow.DIRECT if complexity in (Complexity.TRIVIAL, Complexity.SMALL)
                else Workflow.LIGHT)
    elif intent is Intent.PROMPT_ENGINEERING:
        tier = Workflow.LIGHT
    elif complexity is Complexity.TRIVIAL:
        tier = Workflow.DIRECT
    elif complexity is Complexity.SMALL:
        tier = Workflow.LIGHT
    elif complexity is Complexity.MODERATE:
        tier = (Workflow.PLANNED if intent in (Intent.BUILD, Intent.REFACTOR, Intent.PLAN)
                else Workflow.LIGHT)
    else:
        tier = Workflow.FULL

    # A code-changing intent with no concrete target is an underspecified change,
    # not a one-step edit. DIRECT would mean editing whatever looked plausible,
    # so raise that case to LIGHT: classify, ask, then act. This is a floor only;
    # it never lowers a heavier tier.
    if tier is Workflow.DIRECT and intent in _CODE_CHANGING and not has_target:
        return Workflow.LIGHT
    return tier


def classify(prompt: str) -> Classification:
    """Classify a prompt. Deterministic, pure, and safe on any input."""
    if not isinstance(prompt, str):
        prompt = ""
    text = prompt.strip()

    intent, intent_signal = _first_intent(text)
    score, complexity_signals = complexity_score(text)
    complexity = _bucket(score)
    domains = detect_domains(text)
    ambiguities = ambiguity_findings(text)
    contradictions = contradictory(text)
    injections = detect_injection(text)

    flags: list[str] = []
    signals: list[Signal] = []
    if intent_signal:
        signals.append(intent_signal)
    signals.extend(complexity_signals)

    if ambiguities:
        flags.append("ambiguous")
        signals.append(Signal("ambiguity", "unclear request", 0.7, "; ".join(ambiguities)))
    if contradictions:
        flags.append("contradictory")
        for item in contradictions:
            signals.append(Signal("contradiction", "conflicting requirement", 0.55, item))
    if injections:
        flags.append("injection_suspected")
        signals.extend(injections)
    if _DESTRUCTIVE.search(text):
        flags.append("destructive")
        signals.append(Signal("risk", "destructive operation named", 0.7,
                              _DESTRUCTIVE.search(text).group(0)))
    if intent in (Intent.RESEARCH, Intent.REVIEW) or re.search(
            r"\b(latest|current|as of|newest|version|docs?)\b", text, re.I):
        flags.append("needs_research")
    if _HARNESS_TAG.match(prompt):
        flags.append("harness_event")
    if _ACCEPTANCE.search(text):
        flags.append("has_acceptance_criteria")
    if len(domains) >= 3:
        flags.append("cross_layer")
        signals.append(Signal("scope", "multiple layers", 0.6, ", ".join(domains)))

    workflow = choose_workflow(intent, complexity, flags, has_anchor(text))
    return Classification(
        intent=intent,
        complexity=complexity,
        priority=detect_priority(text),
        output_shape=detect_output(text),
        workflow=workflow,
        domains=domains,
        flags=flags,
        ambiguities=ambiguities,
        signals=signals,
        scores={
            "complexity": score,
            "ambiguity": min(1.0, len(ambiguities) * 0.35),
            "risk": 1.0 if "destructive" in flags else (0.5 if "injection_suspected" in flags else 0.0),
            "research_need": 1.0 if "needs_research" in flags else 0.0,
        },
        word_count=_words(text),
    )
