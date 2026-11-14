"""The eval harness has to be able to fail.

A harness that reports 100% when its dataset is empty, unparsable, or named
after no evaluator is worse than no harness: it turns "we measured nothing"
into "we measured everything and it passed". These tests pin the three ways
that used to happen.
"""

from __future__ import annotations

import json

import pytest

from zyrompts.evals import EvalReport, load_dataset, run_all, run_suite


def test_a_clean_suite_is_clean(tmp_path):
    dataset = tmp_path / "policy.jsonl"
    dataset.write_text(json.dumps({
        "id": "p1", "tool": "Bash", "args": {"command": "ls -la"},
        "autonomy": "read-only", "expect": {"decision": "allow"},
    }) + "\n", encoding="utf-8")

    report = run_suite("policy", dataset)
    assert report.total == 1
    assert report.passed == 1
    assert report.is_clean()


def test_an_entirely_malformed_dataset_is_not_a_pass(tmp_path):
    """It used to load zero cases and report 0/0, which reads as success."""
    dataset = tmp_path / "policy.jsonl"
    dataset.write_text("{bad json\n{also bad\n", encoding="utf-8")

    report = run_suite("policy", dataset)
    assert report.total == 0
    assert len(report.problems) == 2
    assert not report.is_clean()
    assert any("invalid JSON" in problem for problem in report.problems)


def test_a_dataset_with_no_evaluator_is_reported(tmp_path):
    """The suite name selects the evaluator; a mismatch used to be silent."""
    dataset = tmp_path / "mystery.jsonl"
    dataset.write_text(json.dumps({"id": "m1"}) + "\n", encoding="utf-8")

    report = run_suite("mystery", dataset)
    assert report.total == 0
    assert any("no evaluator" in problem for problem in report.problems)
    assert not report.is_clean()


def test_one_bad_line_does_not_kill_the_rest(tmp_path):
    dataset = tmp_path / "policy.jsonl"
    good = json.dumps({
        "id": "p1", "tool": "Bash", "args": {"command": "rm -rf /"},
        "autonomy": "yolo", "expect": {"decision": "deny"},
    })
    dataset.write_text("{bad\n" + good + "\n", encoding="utf-8")

    report = run_suite("policy", dataset)
    assert report.total == 1
    assert report.passed == 1
    # The suite still ran, but it is not clean: a line was dropped.
    assert len(report.problems) == 1
    assert not report.is_clean()


def test_a_failing_case_is_not_clean(tmp_path):
    dataset = tmp_path / "policy.jsonl"
    dataset.write_text(json.dumps({
        "id": "p1", "tool": "Bash", "args": {"command": "rm -rf /"},
        "autonomy": "yolo", "expect": {"decision": "allow"},
    }) + "\n", encoding="utf-8")

    report = run_suite("policy", dataset)
    assert report.passed == 0
    assert not report.is_clean()


def test_load_dataset_reports_line_numbers(tmp_path):
    dataset = tmp_path / "x.jsonl"
    dataset.write_text("# a comment\n\n{broken\n", encoding="utf-8")

    cases, problems = load_dataset(dataset)
    assert cases == []
    assert len(problems) == 1
    assert ":3:" in problems[0]


def test_a_dataset_of_non_objects_is_reported(tmp_path):
    dataset = tmp_path / "policy.jsonl"
    dataset.write_text("[1, 2, 3]\n", encoding="utf-8")

    report = run_suite("policy", dataset)
    assert report.total == 0
    assert report.problems


def test_empty_report_is_never_clean():
    assert not EvalReport(suite="policy").is_clean()


def test_run_all_over_the_real_datasets_passes(datasets_dir):
    reports = run_all(datasets_dir)
    assert reports, "no datasets found"
    for report in reports:
        assert report.is_clean(), f"{report.suite}: {report.problems} {report.failures()}"


def test_real_datasets_have_no_load_problems(datasets_dir):
    for path in sorted(datasets_dir.glob("*.jsonl")):
        _cases, problems = load_dataset(path)
        assert problems == [], problems


@pytest.mark.parametrize("suite", ["classification", "injection", "policy", "prompt_score"])
def test_every_suite_has_a_dataset(datasets_dir, suite):
    assert (datasets_dir / f"{suite}.jsonl").is_file()
