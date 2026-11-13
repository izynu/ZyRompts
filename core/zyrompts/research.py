"""Research evidence model.

The framework does not pretend to browse on its own. What it owns is the part
that decides whether research is trustworthy: source reliability, recency,
cross-source agreement, and a confidence score that the planner can act on.

A finding without a source is not a finding. A finding whose only source is a
random blog is not equal to one backed by official documentation, and the
scoring here makes that difference explicit rather than rhetorical.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class SourceTier(str, Enum):
    """Reliability tiers, highest first."""

    OFFICIAL = "official"        # vendor docs, specs, RFCs, the repo itself
    PRIMARY = "primary"          # source code, tests, changelogs, release notes
    SECONDARY = "secondary"      # reputable articles, conference talks, books
    COMMUNITY = "community"      # forums, Stack Overflow, issue threads
    UNVERIFIED = "unverified"    # unknown provenance

    @property
    def weight(self) -> float:
        return {
            SourceTier.OFFICIAL: 1.0,
            SourceTier.PRIMARY: 0.9,
            SourceTier.SECONDARY: 0.6,
            SourceTier.COMMUNITY: 0.4,
            SourceTier.UNVERIFIED: 0.15,
        }[self]


_OFFICIAL_HOSTS = (
    "docs.python.org", "peps.python.org", "developer.mozilla.org", "docs.github.com",
    "kubernetes.io", "docs.docker.com", "www.postgresql.org", "dev.mysql.com",
    "nodejs.org", "react.dev", "vuejs.org", "docs.aws.amazon.com", "cloud.google.com",
    "learn.microsoft.com", "docs.anthropic.com", "platform.openai.com",
    "ai.google.dev", "datatracker.ietf.org", "www.rfc-editor.org", "spec.whatwg.org",
)
_COMMUNITY_HOSTS = ("stackoverflow.com", "reddit.com", "news.ycombinator.com",
                    "medium.com", "dev.to", "quora.com")


def classify_source(url: str) -> SourceTier:
    """Infer a reliability tier from a URL or path."""
    lowered = (url or "").lower()
    if not lowered:
        return SourceTier.UNVERIFIED
    if lowered.startswith(("file://", "./", "/")) or re.match(r"^[\w./-]+\.(py|js|ts|go|rs|md|json|ya?ml)$", lowered):
        return SourceTier.PRIMARY
    if any(host in lowered for host in _OFFICIAL_HOSTS):
        return SourceTier.OFFICIAL
    if "github.com" in lowered and ("/blob/" in lowered or "/raw/" in lowered):
        return SourceTier.PRIMARY
    if any(host in lowered for host in _COMMUNITY_HOSTS):
        return SourceTier.COMMUNITY
    if lowered.startswith("http"):
        return SourceTier.SECONDARY
    return SourceTier.UNVERIFIED


@dataclass
class Finding:
    claim: str
    source: str
    tier: SourceTier
    retrieved: str = ""          # ISO date, YYYY-MM-DD
    supports: bool = True        # False marks a contradicting source
    notes: str = ""

    def age_days(self, today: date | None = None) -> int | None:
        if not self.retrieved:
            return None
        try:
            stamp = datetime.strptime(self.retrieved, "%Y-%m-%d").date()
        except ValueError:
            return None
        return ((today or date.today()) - stamp).days

    def to_dict(self) -> dict:
        return {
            "claim": self.claim,
            "source": self.source,
            "tier": self.tier.value,
            "retrieved": self.retrieved,
            "supports": self.supports,
            "notes": self.notes,
        }


@dataclass
class ResearchReport:
    question: str
    findings: list[Finding] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    summary: str = ""

    # --- scoring ------------------------------------------------------------

    def confidence(self) -> float:
        """0..1 confidence for the question as a whole.

        Two independent official sources agreeing is near-certain. A single
        community post is weak. A contradiction caps confidence at 0.4 no
        matter how many sources agree, because unresolved conflict is the
        thing that actually breaks downstream plans.
        """
        if not self.findings:
            return 0.0
        support = [f for f in self.findings if f.supports]
        contradict = [f for f in self.findings if not f.supports]
        if contradict:
            return min(0.4, max(f.tier.weight for f in support) * 0.4 if support else 0.2)

        weights = sorted((f.tier.weight for f in support), reverse=True)
        best = weights[0] if weights else 0.0
        corroboration = min(0.3, 0.15 * (len(weights) - 1))
        distinct = len({f.source for f in support})
        diversity = min(0.2, 0.1 * (distinct - 1))
        staleness_penalty = 0.0
        ages = [a for a in (f.age_days() for f in support) if a is not None]
        if ages and max(ages) > 730:
            staleness_penalty = 0.2
        elif ages and max(ages) > 365:
            staleness_penalty = 0.1
        return max(0.0, min(1.0, best * 0.5 + corroboration + diversity - staleness_penalty))

    def freshness(self) -> str:
        ages = [a for a in (f.age_days() for f in self.findings) if a is not None]
        if not ages:
            return "unknown"
        newest = min(ages)
        if newest <= 90:
            return "fresh"
        if newest <= 365:
            return "current"
        if newest <= 730:
            return "aging"
        return "stale"

    def gaps_from(self, required_claims: list[str]) -> list[str]:
        """Report required questions that no finding answers."""
        covered = " ".join(f.claim.lower() for f in self.findings)
        return [claim for claim in required_claims
                if not all(word in covered for word in claim.lower().split()[:2])]

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "confidence": round(self.confidence(), 2),
            "freshness": self.freshness(),
            "gaps": list(self.gaps),
            "findings": [f.to_dict() for f in self.findings],
            "summary": self.summary,
        }

    def to_markdown(self) -> str:
        lines = [f"# Research: {self.question}", "",
                 f"Confidence: {self.confidence():.2f} ({self.freshness()})", ""]
        if self.summary:
            lines.extend([self.summary, ""])
        lines.append("## Findings")
        for finding in self.findings:
            marker = "supports" if finding.supports else "contradicts"
            lines.append(f"- [{finding.tier.value}] {finding.claim} ({marker})")
            lines.append(f"  - source: {finding.source}")
        if self.gaps:
            lines.extend(["", "## Gaps"])
            lines.extend(f"- {gap}" for gap in self.gaps)
        return "\n".join(lines) + "\n"


def verify_claim(claim: str, report: ResearchReport) -> dict:
    """Return a verification verdict for one claim against the report."""
    needle = set(re.findall(r"\w+", claim.lower()))
    best: Finding | None = None
    best_overlap = 0.0
    for finding in report.findings:
        words = set(re.findall(r"\w+", finding.claim.lower()))
        if not words:
            continue
        overlap = len(needle & words) / max(1, len(needle))
        if overlap > best_overlap:
            best, best_overlap = finding, overlap
    if best is None or best_overlap < 0.5:
        return {"claim": claim, "status": "UNVERIFIED", "confidence": 0.0,
                "reason": "no source addresses this claim"}
    status = "CONFIRMED" if best.supports and best.tier.weight >= 0.6 else "UNVERIFIED"
    return {"claim": claim, "status": status,
            "confidence": round(best.tier.weight * best_overlap, 2),
            "source": best.source, "reason": f"{best.tier.value} source, overlap {best_overlap:.2f}"}
