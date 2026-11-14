"""Persistent project state.

A project's state is a single JSON document under ``.zyrompts/state/project.json``.
It survives sessions, context compaction and crashes, so work can resume
without re-deriving what was already decided.

Design rules:
- Writes are atomic (temp file + rename) so a crash mid-write cannot corrupt
  the only copy of the state.
- Every mutation appends to an append-only event log so history is auditable.
- The state is schema-versioned; a future version refuses to silently
  downgrade rather than mis-reading fields.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

STATE_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _redact_fields(fields: dict) -> dict:
    """Redact every string value, recursing into lists and dicts.

    Imported lazily so `state` stays importable without `policy`, which the
    CLI already imports: a module-level import would make the dependency
    circular the day policy starts using state.
    """
    from .policy import redact_secrets

    def _walk(value):
        if isinstance(value, str):
            return redact_secrets(value)[0]
        if isinstance(value, list):
            return [_walk(item) for item in value]
        if isinstance(value, dict):
            return {key: _walk(item) for key, item in value.items()}
        return value

    return {key: _walk(value) for key, value in fields.items()}


@dataclass
class Task:
    id: str
    title: str
    status: str = "pending"      # pending | in_progress | done | skipped | failed
    depends_on: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProjectState:
    version: int = STATE_VERSION
    goal: str = ""
    phase: str = "intake"
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    tasks: list[Task] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    known_issues: list[str] = field(default_factory=list)
    plan_versions: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    # --- derived views ------------------------------------------------------

    @property
    def done(self) -> list[Task]:
        return [t for t in self.tasks if t.status == "done"]

    @property
    def blocked(self) -> list[Task]:
        """Tasks whose dependencies are not all done."""
        done_ids = {t.id for t in self.done}
        return [t for t in self.tasks
                if t.status in ("pending", "in_progress")
                and any(dep not in done_ids for dep in t.depends_on)]

    @property
    def next_task(self) -> Task | None:
        done_ids = {t.id for t in self.done}
        for task in self.tasks:
            if task.status == "pending" and all(dep in done_ids for dep in task.depends_on):
                return task
        return None

    def progress(self) -> dict:
        counts: dict[str, int] = {}
        for task in self.tasks:
            counts[task.status] = counts.get(task.status, 0) + 1
        total = len(self.tasks)
        return {
            "total": total,
            "done": counts.get("done", 0),
            "percent": round(100 * counts.get("done", 0) / total, 1) if total else 0.0,
            "by_status": counts,
            "blocked": len(self.blocked),
        }

    def to_dict(self) -> dict:
        data = asdict(self)
        data["tasks"] = [t.to_dict() for t in self.tasks]
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectState":
        data = dict(data or {})
        version = int(data.get("version", 0))
        if version > STATE_VERSION:
            raise ValueError(
                f"state version {version} is newer than supported {STATE_VERSION}; "
                "upgrade zyrompts rather than risk mis-reading fields")
        tasks = [Task(**{k: v for k, v in t.items() if k in Task.__dataclass_fields__})
                 for t in data.get("tasks", []) if isinstance(t, dict)]
        known = {f.name for f in cls.__dataclass_fields__.values()}
        clean = {k: v for k, v in data.items() if k in known and k != "tasks"}
        return cls(tasks=tasks, **clean)


class StateStore:
    """Atomic, append-only-logged project state on disk."""

    def __init__(self, root: Path | str = ".", state: ProjectState | None = None):
        self.root = Path(root)
        self.dir = self.root / ".zyrompts" / "state"
        self.path = self.dir / "project.json"
        self.log_path = self.dir / "events.jsonl"
        # Set by load() when the on-disk file was unreadable: where the original
        # was moved to, and why. Callers can surface this instead of silently
        # starting a project that looks new.
        self.corrupt_backup: Path | None = None
        self.quarantined_reason: str = ""
        if state is not None:
            self.state = state
        else:
            # Load eagerly. Without this, a store constructed over an existing
            # project starts empty, and the next save() overwrites project.json
            # and destroys the task list. Resuming a session is the normal case,
            # so it must not be the destructive one.
            self.state = ProjectState()
            self.load()

    # --- persistence --------------------------------------------------------

    def load(self) -> ProjectState:
        if not self.path.is_file():
            return self.state
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            # Unparsable JSON is recoverable: degrade to a fresh state so the
            # session is not blocked, but do not leave the broken file where the
            # next save() would overwrite it, which turns a parse error into
            # permanent data loss. Move it aside once, and only once.
            self.corrupt_backup = self._quarantine(exc)
            return self.state
        # A newer schema is a different decision: the file is readable and the
        # running code does not understand it, so proceeding would mis-read
        # fields. Refuse, as the module contract says, rather than replace the
        # user's state with an empty one.
        self.state = ProjectState.from_dict(data)
        return self.state

    def _quarantine(self, reason: Exception) -> Path | None:
        """Move an unreadable state file aside, returning where it went."""
        target = self.path.with_suffix(f".corrupt-{int(time.time())}.json")
        try:
            os.replace(self.path, target)
        except OSError:
            return None
        self.quarantined_reason = f"{type(reason).__name__}: {reason}"
        return target

    def save(self) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state.updated_at = _now()
        payload = json.dumps(self.state.to_dict(), indent=2, sort_keys=False)
        fd, tmp = tempfile.mkstemp(dir=str(self.dir), prefix=".project.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        return self.path

    def log(self, event: str, **fields) -> None:
        """Append one event, redacting credential-shaped values first.

        The event log is the one place a session's own words are written to
        disk and then kept. A goal, a task title or a note routinely quotes a
        command, a config line or a transcript, which is exactly how a token
        ends up in a file that outlives the session. Redaction happens here
        rather than at the call sites so a new mutation cannot forget it.
        """
        self.dir.mkdir(parents=True, exist_ok=True)
        entry = {"at": _now(), "event": event, **_redact_fields(fields)}
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    def history(self, limit: int = 50) -> list[dict]:
        if not self.log_path.is_file():
            return []
        entries: list[dict] = []
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries[-limit:]

    # --- mutations ----------------------------------------------------------

    def set_goal(self, goal: str) -> None:
        self.state.goal = goal
        self.save()
        self.log("goal_set", goal=goal)

    def set_phase(self, phase: str) -> None:
        self.state.phase = phase
        self.save()
        self.log("phase_set", phase=phase)

    def add_task(self, title: str, task_id: str | None = None,
                 depends_on: list[str] | None = None) -> Task:
        task_id = task_id or f"t{len(self.state.tasks) + 1}"
        task = Task(id=task_id, title=title, depends_on=depends_on or [])
        self.state.tasks.append(task)
        self.save()
        self.log("task_added", id=task_id, title=title)
        return task

    def complete_task(self, task_id: str, evidence: list[str] | None = None) -> Task | None:
        for task in self.state.tasks:
            if task.id == task_id:
                task.status = "done"
                task.evidence.extend(evidence or [])
                self.save()
                self.log("task_done", id=task_id, evidence=evidence or [])
                return task
        return None

    def fail_task(self, task_id: str, reason: str) -> Task | None:
        for task in self.state.tasks:
            if task.id == task_id:
                task.status = "failed"
                task.notes = reason
                self.save()
                self.log("task_failed", id=task_id, reason=reason)
                return task
        return None

    def record_decision(self, decision: str, rationale: str, alternatives: list[str] | None = None) -> None:
        entry = {"at": _now(), "decision": decision, "rationale": rationale,
                 "alternatives": alternatives or []}
        self.state.decisions.append(entry)
        self.save()
        self.log("decision", **entry)

    def add_known_issue(self, issue: str) -> None:
        if issue not in self.state.known_issues:
            self.state.known_issues.append(issue)
            self.save()
            self.log("known_issue", issue=issue)

    def snapshot_plan(self, plan_text: str, note: str = "") -> dict:
        """Version the plan so history survives edits."""
        entry = {
            "version": len(self.state.plan_versions) + 1,
            "at": _now(),
            "note": note,
            "sha_len": len(plan_text),
            "body": plan_text,
        }
        self.state.plan_versions.append(entry)
        self.save()
        self.log("plan_version", version=entry["version"], note=note)
        return entry
