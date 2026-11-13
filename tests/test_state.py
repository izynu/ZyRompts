"""State contract: atomic writes, schema versioning, append-only history."""

from __future__ import annotations

import json

import pytest

from zyrompts.state import STATE_VERSION, ProjectState, StateStore, Task


def test_new_store_starts_empty(tmp_path):
    store = StateStore(tmp_path)
    assert store.state.tasks == []
    assert store.state.phase == "intake"


def test_save_then_load_roundtrips(tmp_path):
    store = StateStore(tmp_path)
    store.set_goal("ship the rate limiter")
    store.add_task("write the limiter", task_id="t1")

    reloaded = StateStore(tmp_path)
    assert reloaded.state.goal == "ship the rate limiter"
    assert [t.id for t in reloaded.state.tasks] == ["t1"]


def test_constructing_over_existing_state_does_not_destroy_it(tmp_path):
    """Regression: __init__ used to start empty, so save() wiped the task list."""
    first = StateStore(tmp_path)
    first.add_task("keep me", task_id="keep")

    second = StateStore(tmp_path)
    second.set_phase("execute")

    reloaded = StateStore(tmp_path)
    assert [t.id for t in reloaded.state.tasks] == ["keep"]
    assert reloaded.state.phase == "execute"


def test_save_is_atomic_and_leaves_no_temp_files(tmp_path):
    store = StateStore(tmp_path)
    store.set_goal("x")
    leftovers = [p.name for p in tmp_path.rglob("*.tmp*")]
    assert leftovers == []


def test_state_file_is_valid_json(tmp_path):
    store = StateStore(tmp_path)
    store.set_goal("x")
    json.loads(store.path.read_text(encoding="utf-8"))


def test_refuses_to_load_a_newer_schema(tmp_path):
    store = StateStore(tmp_path)
    store.set_goal("x")
    data = json.loads(store.path.read_text(encoding="utf-8"))
    data["version"] = STATE_VERSION + 1
    store.path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError):
        StateStore(tmp_path)


def test_corrupt_state_does_not_crash_construction(tmp_path):
    store = StateStore(tmp_path)
    store.set_goal("x")
    store.path.write_text("{not json", encoding="utf-8")
    # A corrupt file degrades to a fresh state rather than blocking the session.
    assert StateStore(tmp_path).state.tasks == []


def test_complete_task_records_evidence(tmp_path):
    store = StateStore(tmp_path)
    store.add_task("do it", task_id="t1")
    store.complete_task("t1", evidence=["pytest: 12 passed"])
    assert store.state.tasks[0].status == "done"
    assert "pytest: 12 passed" in store.state.tasks[0].evidence


def test_progress_reports_percent_and_blocked(tmp_path):
    store = StateStore(tmp_path)
    store.add_task("a", task_id="a")
    store.add_task("b", task_id="b", depends_on=["a"])
    store.complete_task("a")
    progress = store.state.progress()
    assert progress["total"] == 2
    assert progress["done"] == 1
    assert progress["percent"] == 50.0


def test_blocked_task_is_not_next(tmp_path):
    store = StateStore(tmp_path)
    store.add_task("a", task_id="a")
    store.add_task("b", task_id="b", depends_on=["a"])
    assert store.state.next_task.id == "a"
    store.complete_task("a")
    assert store.state.next_task.id == "b"


def test_log_is_append_only_jsonl(tmp_path):
    store = StateStore(tmp_path)
    store.log("phase", to="plan")
    store.log("phase", to="execute")
    lines = [l for l in store.log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    for line in lines:
        json.loads(line)


def test_history_reads_back_entries(tmp_path):
    store = StateStore(tmp_path)
    store.record_decision("use redis", "it is already deployed")
    entry = store.history()[-1]
    assert entry["event"] == "decision"
    assert entry["decision"] == "use redis"


def test_history_skips_corrupt_lines(tmp_path):
    store = StateStore(tmp_path)
    store.log("phase", to="plan")
    with store.log_path.open("a", encoding="utf-8") as handle:
        handle.write("{broken\n")
    store.log("phase", to="execute")
    assert len(store.history()) == 2


def test_unknown_task_id_returns_none(tmp_path):
    store = StateStore(tmp_path)
    assert store.complete_task("nope") is None
    assert store.state.tasks == []


def test_task_dependencies_are_preserved(tmp_path):
    store = StateStore(tmp_path)
    store.add_task("first", task_id="a")
    store.add_task("second", task_id="b", depends_on=["a"])
    reloaded = StateStore(tmp_path)
    assert reloaded.state.tasks[1].depends_on == ["a"]


def test_plan_versions_are_appended_not_replaced(tmp_path):
    store = StateStore(tmp_path)
    store.snapshot_plan("v1", note="first")
    store.snapshot_plan("v2", note="second")
    assert [p["version"] for p in store.state.plan_versions] == [1, 2]


def test_known_issues_are_deduplicated(tmp_path):
    store = StateStore(tmp_path)
    store.add_known_issue("flaky test")
    store.add_known_issue("flaky test")
    assert store.state.known_issues == ["flaky test"]


def test_project_state_to_from_dict_is_stable():
    original = ProjectState(goal="g", phase="plan")
    original.tasks.append(Task(id="t", title="x"))
    roundtripped = ProjectState.from_dict(original.to_dict())
    assert roundtripped.to_dict() == original.to_dict()


def test_from_dict_ignores_unknown_fields():
    state = ProjectState.from_dict({"version": 1, "goal": "g", "future_field": 1})
    assert state.goal == "g"
