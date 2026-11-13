"""Research contract: source tiering, corroboration, and honest confidence.

The property that matters: confidence is derived from the evidence, and a
contradicted claim cannot come out confident.
"""

from __future__ import annotations

import pytest

from zyrompts.research import (
    Finding,
    ResearchReport,
    SourceTier,
    classify_source,
    verify_claim,
)


@pytest.mark.parametrize("url,tier", [
    ("https://docs.python.org/3/library/asyncio.html", SourceTier.OFFICIAL),
    ("https://peps.python.org/pep-0008/", SourceTier.OFFICIAL),
    ("https://github.com/python/cpython/blob/main/README.rst", SourceTier.PRIMARY),
    ("https://example.com/blog/post", SourceTier.SECONDARY),
    ("https://stackoverflow.com/questions/123", SourceTier.COMMUNITY),
    ("https://reddit.com/r/python/comments/x", SourceTier.COMMUNITY),
])
def test_classify_source(url, tier):
    assert classify_source(url) is tier


def test_unknown_http_url_is_secondary():
    """An unrecognised https host is still a published page, not noise."""
    assert classify_source("https://some-random-site.example/x") is SourceTier.SECONDARY


def test_non_url_is_unverified():
    assert classify_source("") is SourceTier.UNVERIFIED
    assert classify_source("remember what I said") is SourceTier.UNVERIFIED


def test_official_source_outranks_community():
    assert SourceTier.OFFICIAL.weight > SourceTier.COMMUNITY.weight
    assert SourceTier.COMMUNITY.weight > SourceTier.UNVERIFIED.weight


def test_single_official_finding_is_moderately_confident():
    report = ResearchReport(question="q")
    report.findings.append(Finding("asyncio.run is the entry point",
                                   "https://docs.python.org/3/library/asyncio.html",
                                   SourceTier.OFFICIAL, supports=True))
    confidence = report.confidence()
    assert 0.0 < confidence <= 1.0


def test_corroborating_sources_raise_confidence():
    single = ResearchReport(question="q")
    single.findings.append(Finding("claim", "https://docs.python.org/3/", SourceTier.OFFICIAL))
    many = ResearchReport(question="q")
    many.findings.extend([
        Finding("claim", "https://docs.python.org/3/", SourceTier.OFFICIAL),
        Finding("claim", "https://peps.python.org/pep-1/", SourceTier.OFFICIAL),
    ])
    assert many.confidence() >= single.confidence()


def test_a_contradiction_caps_confidence():
    report = ResearchReport(question="q")
    report.findings.extend([
        Finding("claim", "https://docs.python.org/3/", SourceTier.OFFICIAL, supports=True),
        Finding("claim", "https://example.com/blog", SourceTier.SECONDARY, supports=False),
    ])
    assert report.confidence() <= 0.4


def test_empty_report_has_zero_confidence():
    assert ResearchReport(question="q").confidence() == 0.0


def test_verify_claim_reports_support_and_confidence():
    report = ResearchReport(question="q")
    report.findings.append(Finding("the GIL is per-interpreter in 3.12",
                                   "https://docs.python.org/3/", SourceTier.OFFICIAL))
    result = verify_claim("the GIL is per-interpreter in 3.12", report)
    assert "confidence" in result
    assert result["source"] == "https://docs.python.org/3/"
    assert result["status"] == "CONFIRMED"


def test_verify_claim_flags_an_unsupported_claim():
    report = ResearchReport(question="q")
    report.findings.append(Finding("unrelated", "https://example.com", SourceTier.SECONDARY))
    result = verify_claim("a claim nothing supports", report)
    assert result["status"] == "UNVERIFIED"
    assert result["confidence"] == 0.0


def test_markdown_report_names_sources_and_confidence():
    report = ResearchReport(question="is it fast")
    report.findings.append(Finding("it is fast", "https://docs.python.org/3/",
                                   SourceTier.OFFICIAL))
    text = report.to_markdown()
    assert "docs.python.org" in text


def test_gaps_are_carried_through():
    report = ResearchReport(question="q", gaps=["no benchmark data"])
    assert "no benchmark data" in report.to_markdown()
