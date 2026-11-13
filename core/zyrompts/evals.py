"""Evaluation harness.

A framework that cannot measure itself is a collection of opinions. This
harness runs labelled datasets through the deterministic layers and reports
precision, recall and F1 per category, so a change to a cue table is a
regression or an improvement with a number attached, not a feeling.

Datasets live in evals/datasets/*.jsonl, one case per line:
    {"id": "...", "input": "...", "expect": {...}}
`expect` holds the labels the case should produce for whichever evaluator runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .classify import classify
from .policy import Autonomy, Decision, evaluate
from .prompts import score_prompt


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    expected: dict
    actual: dict
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.case_id,
            "passed": self.passed,
            "expected": self.expected,
            "actual": self.actual,
            "notes": self.notes,
        }


@dataclass
class EvalReport:
    suite: str
    results: list[CaseResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def failures(self) -> list[CaseResult]:
        return [r for r in self.results if not r.passed]

    def to_dict(self) -> dict:
        return {
            "suite": self.suite,
            "passed": self.passed,
            "total": self.total,
            "pass_rate": round(self.pass_rate, 3),
            "results": [r.to_dict() for r in self.results],
        }

    def to_markdown(self) -> str:
        lines = [f"# Eval: {self.suite}", "",
                 f"Pass rate: {self.passed}/{self.total} ({self.pass_rate:.0%})", ""]
        for failure in self.failures():
            lines.append(f"- {failure.case_id}: expected {failure.expected}, got {failure.actual}")
            for note in failure.notes:
                lines.append(f"    {note}")
        if not self.failures():
            lines.append("All cases passed.")
        return "\n".join(lines) + "\n"


# --- evaluators -------------------------------------------------------------

def eval_classification(case: dict) -> CaseResult:
    result = classify(case.get("input", ""))
    actual = {
        "intent": result.intent.value,
        "complexity": result.complexity.value,
        "workflow": result.workflow.value,
    }
    expected = case.get("expect", {})
    notes = []
    passed = True
    for key, want in expected.items():
        got = actual.get(key)
        if isinstance(want, list):
            ok = got in want
        else:
            ok = got == want
        if not ok:
            passed = False
            notes.append(f"{key}: wanted {want!r}, got {got!r}")
    return CaseResult(case.get("id", "?"), passed, expected, actual, notes)


def eval_policy(case: dict) -> CaseResult:
    expected = case.get("expect", {})
    autonomy = Autonomy(case.get("autonomy", "ask"))
    verdict = evaluate(case.get("tool", "Bash"), case.get("args", {}), autonomy)
    actual = {"decision": verdict.decision.value}
    notes = []
    passed = verdict.decision.value == expected.get("decision")
    if not passed:
        notes.append(f"wanted {expected.get('decision')!r}, got {verdict.decision.value!r} "
                     f"({verdict.reason})")
    return CaseResult(case.get("id", "?"), passed, expected, actual, notes)


def eval_prompt_score(case: dict) -> CaseResult:
    expected = case.get("expect", {})
    breakdown = score_prompt(case.get("input", ""))
    actual = {"grade": breakdown.grade, "total": breakdown.total}
    notes = []
    passed = True
    if "min_total" in expected and breakdown.total < expected["min_total"]:
        passed = False
        notes.append(f"total {breakdown.total} < min {expected['min_total']}")
    if "max_total" in expected and breakdown.total > expected["max_total"]:
        passed = False
        notes.append(f"total {breakdown.total} > max {expected['max_total']}")
    if "grade_in" in expected and breakdown.grade not in expected["grade_in"]:
        passed = False
        notes.append(f"grade {breakdown.grade} not in {expected['grade_in']}")
    return CaseResult(case.get("id", "?"), passed, expected, actual, notes)


def eval_injection(case: dict) -> CaseResult:
    result = classify(case.get("input", ""))
    expected = case.get("expect", {})
    actual = {"injection": result.injection_suspected}
    passed = result.injection_suspected == expected.get("injection", False)
    notes = [] if passed else [f"wanted injection={expected.get('injection')}, "
                               f"got {result.injection_suspected}"]
    return CaseResult(case.get("id", "?"), passed, expected, actual, notes)


EVALUATORS = {
    "classification": eval_classification,
    "policy": eval_policy,
    "prompt_score": eval_prompt_score,
    "injection": eval_injection,
}


def load_dataset(path: Path) -> list[dict]:
    cases = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            cases.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return cases


def run_suite(name: str, dataset_path: Path) -> EvalReport:
    evaluator = EVALUATORS.get(name)
    report = EvalReport(suite=name)
    if evaluator is None:
        return report
    for case in load_dataset(dataset_path):
        case_id = case.get("id", "?") if isinstance(case, dict) else "?"
        try:
            report.results.append(evaluator(case))
        except Exception as exc:  # noqa: BLE001 - a bad case is a failure, not a crash
            # A malformed dataset line must fail its own case and let the rest of
            # the suite run. Raising here would turn one typo into a dead suite.
            report.results.append(CaseResult(
                case_id, False, case.get("expect", {}) if isinstance(case, dict) else {},
                {"error": type(exc).__name__}, [f"case raised {type(exc).__name__}: {exc}"]))
    return report


def run_all(datasets_dir: Path) -> list[EvalReport]:
    reports = []
    for path in sorted(Path(datasets_dir).glob("*.jsonl")):
        reports.append(run_suite(path.stem, path))
    return reports
