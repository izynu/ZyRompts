"""Review contract: adversarial findings, severity ordering, verdict derivation.

The property under test is the one that makes review worth doing: a finding is
only reported if it survives an attempt to refute it, and the verdict follows
from the findings rather than from the reviewer's mood.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zyrompts.review import (
    Confidence,
    Finding,
    ReviewReport,
    Severity,
    critique_diff,
    critique_plan,
    critique_requirements,
    try_refute,
)


def _finding(severity=Severity.HIGH, confidence=Confidence.CONFIRMED) -> Finding:
    return Finding(title="t", description="d", evidence="e",
                   severity=severity, confidence=confidence)


def test_empty_plan_is_critiqued_not_accepted():
    report = critique_plan("")
    assert report.findings
    assert report.verdict() in ("BLOCK", "REVISE")


def test_plan_without_affected_files_is_flagged():
    report = critique_plan("# Plan\n\n## Step 1\nDo the thing.\n")
    assert any("affected" in f.title.lower() or "files" in f.description.lower()
               for f in report.findings)


def test_plan_without_verification_is_flagged():
    report = critique_plan("# Plan\n\n## Step 1\nDo the thing.\n\nAffected files: a.py\n")
    assert report.findings


def test_complete_plan_passes():
    plan = (
        "# Plan\n\n## 1. Add the limiter\n"
        "Affected files: src/api/limiter.py\n"
        "Verification: pytest tests/test_limiter.py\n"
        "Acceptance: 429 after 100 requests per minute.\n"
    )
    report = critique_plan(plan)
    assert report.verdict() == "PASS", [f.title for f in report.findings]


def test_plan_naming_a_nonexistent_path_is_flagged():
    plan = ("# Plan\n\n## 1. X\nAffected files: src/does/not/exist.py\n"
            "Verification: pytest\nAcceptance: it works.\n")
    report = critique_plan(plan, existing_paths={"src/real.py"})
    assert any("exist" in f.title.lower() or "exist" in f.description.lower()
               for f in report.findings)


def test_requirements_without_acceptance_criteria_are_flagged():
    report = critique_requirements("Build a fast search feature.")
    assert report.findings


@pytest.mark.parametrize("snippet", [
    "print('debug')\n",
    "console.log(x)\n",
    "TODO: fix this\n",
    "except:\n    pass\n",
    "eval(user_input)\n",
    "password = 'hunter2hunter2'\n",
])
def test_diff_review_catches_known_smells(snippet):
    report = critique_diff(f"+{snippet}")
    assert report.findings, f"missed {snippet!r}"


def test_clean_diff_has_no_findings():
    report = critique_diff("+def add(a, b):\n+    return a + b\n")
    assert report.findings == []
    assert report.verdict() == "PASS"


@pytest.mark.parametrize("severity", [Severity.CRITICAL, Severity.HIGH])
def test_verdict_blocks_on_critical_or_high(severity):
    """A confirmed HIGH is not mergeable, so it blocks rather than revises."""
    report = ReviewReport(subject="x", findings=[_finding(severity)])
    assert report.verdict() == "BLOCK"


def test_verdict_revises_on_medium():
    report = ReviewReport(subject="x", findings=[_finding(Severity.MEDIUM)])
    assert report.verdict() == "REVISE"


def test_verdict_passes_on_low_only():
    report = ReviewReport(subject="x", findings=[_finding(Severity.LOW)])
    assert report.verdict() == "PASS"


def test_refuted_findings_do_not_affect_the_verdict():
    refuted = try_refute(_finding(Severity.CRITICAL), "the guard upstream prevents it")
    report = ReviewReport(subject="x", findings=[refuted])
    assert report.surviving() == []
    assert report.verdict() == "PASS"


def test_try_refute_keeps_the_refutation_text():
    refuted = try_refute(_finding(), "counter-evidence")
    assert refuted.refuted is True
    assert refuted.refutation


def test_counts_group_by_severity():
    report = ReviewReport(subject="x", findings=[
        _finding(Severity.HIGH), _finding(Severity.LOW), _finding(Severity.LOW)])
    counts = report.counts()
    assert counts["by_severity"]["high"] == 1
    assert counts["by_severity"]["low"] == 2
    assert counts["surviving"] == 3


def test_markdown_report_names_the_verdict_and_evidence():
    report = ReviewReport(subject="src/x.py", findings=[_finding(Severity.MEDIUM)])
    text = report.to_markdown()
    assert "REVISE" in text
    assert "Evidence: e" in text


# --- chapter detection ------------------------------------------------------

def test_structural_headings_are_not_graded_as_chapters():
    """A plan template's "Out of scope" section has no affected files by design."""
    plan = ("# Plan\n\n## Context\nwhy\n\n## Chapters\n\n## 1. Work\n"
            "Affected files: a.py\nVerification: pytest\n\n"
            "## Out of scope\n- nothing\n\n## Rollback\nrevert\n\n## Open questions\n- none\n")
    report = critique_plan(plan)
    assert report.verdict() == "PASS", [f.title for f in report.surviving()]


def test_a_real_chapter_missing_its_files_is_still_flagged():
    plan = "# Plan\n\n## Context\nwhy\n\n## 1. Work\nno files named here\n"
    titles = [f.title for f in critique_plan(plan).surviving()]
    assert "Chapter 1 missing Affected files" in titles


def test_plan_template_in_this_repo_passes_its_own_critique():
    template = Path(__file__).resolve().parent.parent / "templates" / "plan.md"
    report = critique_plan(template.read_text(encoding="utf-8"))
    assert report.verdict() == "PASS", [f.title for f in report.surviving()]


def test_specification_template_passes_its_own_critique():
    template = Path(__file__).resolve().parent.parent / "templates" / "specification.md"
    report = critique_requirements(template.read_text(encoding="utf-8"))
    assert report.verdict() == "PASS", [f.title for f in report.surviving()]
