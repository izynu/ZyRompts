"""Independent review: critique a plan, a diff, or a claim.

The core discipline is adversarial refutation. A finding is not written down
until an attempt to refute it has failed, and every surviving finding carries a
confidence grade and evidence. That is what makes a review worth reading: it
reports what could not be refuted, not what sounded plausible.

This module is deterministic where it can be (structural checks that need no
model) and provides the data model for model-driven review where it cannot.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "critical"   # data loss, security hole, breaks production
    HIGH = "high"           # wrong behavior on a realistic path
    MEDIUM = "medium"       # edge case, maintainability, missing test
    LOW = "low"             # style, naming, docs
    INFO = "info"           # observation, no action required


class Confidence(str, Enum):
    CONFIRMED = "CONFIRMED"     # verified against the codebase
    UNVERIFIED = "UNVERIFIED"   # plausible, not checked


@dataclass
class Finding:
    title: str
    description: str
    evidence: str
    severity: Severity
    confidence: Confidence
    suggestion: str = ""
    location: str = ""          # file:line
    refuted: bool = False
    refutation: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "description": self.description,
            "evidence": self.evidence,
            "severity": self.severity.value,
            "confidence": self.confidence.value,
            "suggestion": self.suggestion,
            "location": self.location,
            "refuted": self.refuted,
            "refutation": self.refutation,
        }


@dataclass
class ReviewReport:
    subject: str
    findings: list[Finding] = field(default_factory=list)
    reviewer: str = ""
    notes: list[str] = field(default_factory=list)

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def surviving(self) -> list[Finding]:
        return [f for f in self.findings if not f.refuted]

    def counts(self) -> dict:
        live = self.surviving()
        by_severity: dict[str, int] = {}
        for finding in live:
            by_severity[finding.severity.value] = by_severity.get(finding.severity.value, 0) + 1
        return {
            "total": len(self.findings),
            "surviving": len(live),
            "refuted": len(self.findings) - len(live),
            "by_severity": by_severity,
            "confirmed": sum(1 for f in live if f.confidence is Confidence.CONFIRMED),
            "unverified": sum(1 for f in live if f.confidence is Confidence.UNVERIFIED),
        }

    def verdict(self) -> str:
        live = self.surviving()
        if any(f.severity in (Severity.CRITICAL, Severity.HIGH) for f in live):
            return "BLOCK"
        if any(f.severity is Severity.MEDIUM for f in live):
            return "REVISE"
        return "PASS"

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "reviewer": self.reviewer,
            "counts": self.counts(),
            "verdict": self.verdict(),
            "findings": [f.to_dict() for f in self.findings],
            "notes": list(self.notes),
        }

    def to_markdown(self) -> str:
        counts = self.counts()
        lines = [
            f"# Review: {self.subject}",
            "",
            f"Verdict: {self.verdict()}",
            f"Findings: {counts['surviving']} surviving, {counts['refuted']} refuted "
            f"({counts['confirmed']} CONFIRMED, {counts['unverified']} UNVERIFIED)",
            "",
        ]
        for finding in self.surviving():
            lines.append(f"## {finding.title}")
            lines.append(f"Severity: {finding.severity.value}")
            lines.append(f"Confidence: {finding.confidence.value}")
            lines.append("")
            lines.append(finding.description)
            lines.append("")
            lines.append(f"Evidence: {finding.evidence}")
            if finding.suggestion:
                lines.extend(["", f"Suggestion: {finding.suggestion}"])
            lines.append("")
        if counts["surviving"] == 0:
            lines.append("No findings survived refutation.")
        return "\n".join(lines)


# --- structural checks (no model required) ----------------------------------

_REQUIRED_SECTIONS = ("Affected files", "Verification")

# Headings that organise the document rather than describe a unit of work. The
# plan template ships several of them, and grading "Out of scope" as a chapter
# that forgot its affected files is a false finding: it buries the real ones and
# makes a correct plan fail its own critique.
_NON_CHAPTER_HEADINGS = frozenset({
    "context", "background", "summary", "overview", "status", "goal", "goals",
    "out of scope", "non-goals", "non goals", "rollback", "risks", "risk",
    "open questions", "questions", "references", "notes", "appendix",
    "acceptance criteria", "verification", "timeline", "dependencies",
    "assumptions", "alternatives", "decision", "decisions", "handoff",
    # Container headings: a plan template has a "Chapters" index that holds the
    # chapters. Grading the index as a chapter is the same false finding.
    "chapters", "chapter list", "plan", "method", "approach", "test plan",
    "testing", "definition of done", "scope",
})


def _is_chapter(title: str) -> bool:
    """A chapter heading names a unit of work; a structural heading does not."""
    normalised = re.sub(r"^[\d.)\s-]+", "", title).strip().lower()
    normalised = normalised.rstrip(":").strip()
    return normalised not in _NON_CHAPTER_HEADINGS


def critique_plan(plan_text: str, existing_paths: set[str] | None = None) -> ReviewReport:
    """Run the deterministic part of a plan critique.

    These checks catch the failures that matter most and cost nothing: a
    chapter with no affected files, a chapter with no verification, a path that
    does not exist, and an empty plan masquerading as a finished one.
    """
    report = ReviewReport(subject="plan", reviewer="critic")
    text = plan_text or ""

    if not text.strip():
        report.add(Finding(
            title="Plan is empty",
            description="The plan file has no content.",
            evidence="plan.md is empty or whitespace only",
            severity=Severity.CRITICAL,
            confidence=Confidence.CONFIRMED,
            suggestion="Write the plan before critiquing it.",
        ))
        return report

    sections = re.split(r"(?m)^##\s+", text)[1:]
    chapters = [section for section in sections
                if _is_chapter(section.splitlines()[0].strip() if section.splitlines() else "")]
    if not chapters:
        report.add(Finding(
            title="Plan has no chapters",
            description="The plan is a single blob with no chapter structure.",
            evidence="no '## ' headings found in plan.md",
            severity=Severity.HIGH,
            confidence=Confidence.CONFIRMED,
            suggestion="Split the work into numbered chapters, each with affected files and verification.",
        ))

    for index, chapter in enumerate(chapters, start=1):
        title = chapter.splitlines()[0].strip() if chapter.splitlines() else f"chapter {index}"
        body = chapter.lower()
        for section in _REQUIRED_SECTIONS:
            if section.lower() not in body:
                report.add(Finding(
                    title=f"Chapter {index} missing {section}",
                    description=f"'{title}' does not state its {section.lower()}.",
                    evidence=f"heading '{title}' has no '{section}' section",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.CONFIRMED,
                    suggestion=f"Add a '{section}:' block naming the files and how success is proven.",
                    location=f"plan.md chapter {index}",
                ))

        if existing_paths is not None:
            for path in _paths_in(chapter):
                if path not in existing_paths and not path.startswith(("http", "#")):
                    report.add(Finding(
                        title=f"Chapter {index} references a missing file",
                        description=f"'{title}' names {path}, which does not exist.",
                        evidence=f"path {path!r} not found in the working tree",
                        severity=Severity.HIGH,
                        confidence=Confidence.CONFIRMED,
                        suggestion="Confirm the path or mark it as a file to be created.",
                        location=f"plan.md chapter {index}",
                    ))
    return report


_PATH_RE = re.compile(r"(?<![\w/])((?:\.{0,2}/)?[\w.-]+(?:/[\w.-]+)*\.[A-Za-z0-9]{1,6})\b")


def _paths_in(text: str) -> list[str]:
    found = []
    for match in _PATH_RE.finditer(text):
        candidate = match.group(1)
        if candidate.startswith(("http", "www")):
            continue
        found.append(candidate)
    return found


def critique_requirements(spec_text: str) -> ReviewReport:
    """Check a specification for the properties a plan needs to be buildable."""
    report = ReviewReport(subject="specification", reviewer="critic")
    text = spec_text or ""
    lowered = text.lower()

    checks = [
        ("acceptance criteria", Severity.HIGH,
         "No acceptance criteria. Nothing can be verified complete without them."),
        ("out of scope", Severity.MEDIUM,
         "No out-of-scope section. Scope creep is the default failure of unbounded specs."),
        ("constraint", Severity.MEDIUM,
         "No constraints stated. Without them the implementer will invent them."),
    ]
    for token, severity, message in checks:
        if token not in lowered:
            report.add(Finding(
                title=f"Missing {token}",
                description=message,
                evidence=f"no '{token}' in the specification",
                severity=severity,
                confidence=Confidence.CONFIRMED,
                suggestion=f"Add an explicit '{token}' section.",
            ))
    return report


def critique_diff(diff_text: str) -> ReviewReport:
    """Deterministic diff smell checks: debug leftovers, secrets, oversized hunks."""
    report = ReviewReport(subject="diff", reviewer="code-reviewer")
    text = diff_text or ""
    added = [line[1:] for line in text.splitlines()
             if line.startswith("+") and not line.startswith("+++")]

    smells = [
        (re.compile(r"\b(print|console\.log|dbg!|fmt\.Println|var_dump)\s*\("),
         "Debug output left in the change", Severity.LOW),
        (re.compile(r"\b(TODO|FIXME|XXX|HACK)\b"),
         "Placeholder comment in the change", Severity.LOW),
        (re.compile(r"\b(except\s*:\s*$|catch\s*\(\s*\w*\s*\)\s*\{\s*\})"),
         "Bare except or empty catch swallows errors", Severity.HIGH),
        (re.compile(r"\b(eval|exec)\s*\("),
         "Dynamic code execution in the change", Severity.HIGH),
        (re.compile(r"(password|secret|api[_-]?key)\s*=\s*['\"][^'\"]+['\"]", re.I),
         "Possible hardcoded credential", Severity.CRITICAL),
    ]
    for pattern, title, severity in smells:
        hits = [line for line in added if pattern.search(line)]
        if hits:
            report.add(Finding(
                title=title,
                description=f"{len(hits)} added line(s) match this pattern.",
                evidence=hits[0].strip()[:160],
                severity=severity,
                confidence=Confidence.CONFIRMED,
                suggestion="Remove or justify before merging.",
            ))

    if len(added) > 800:
        report.add(Finding(
            title="Oversized change",
            description=f"{len(added)} added lines in one change.",
            evidence=f"diff adds {len(added)} lines",
            severity=Severity.MEDIUM,
            confidence=Confidence.CONFIRMED,
            suggestion="Split into reviewable changes; large diffs hide defects.",
        ))
    return report


def try_refute(finding: Finding, counter_evidence: str = "") -> Finding:
    """Mark a finding refuted when counter-evidence defeats it.

    Called after an adversarial pass. A finding that survives keeps its grade;
    one that does not is kept in the report but excluded from the verdict, so
    the refutation itself stays auditable.
    """
    if counter_evidence.strip():
        finding.refuted = True
        finding.refutation = counter_evidence.strip()
    return finding
