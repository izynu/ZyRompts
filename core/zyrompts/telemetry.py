"""Telemetry: cost, time, and tool-call accounting.

Local only. Nothing here phones home; the point is that a long agent run can
answer "what did this cost and where did the time go" from a file the user can
read, delete, or export.

Records are appended as JSONL so a crashed run still leaves a usable log.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Rough per-million-token prices in USD. These are planning estimates, not a
# billing source of truth; unknown models fall back to a conservative default.
PRICE_TABLE: dict[str, tuple[float, float]] = {
    "frontier": (15.0, 75.0),
    "standard": (3.0, 15.0),
    "fast": (0.8, 4.0),
    "default": (3.0, 15.0),
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Record:
    kind: str
    name: str
    at: str = field(default_factory=_now)
    duration_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tier: str = "default"
    ok: bool = True
    detail: str = ""

    def cost(self) -> float:
        inp, out = PRICE_TABLE.get(self.tier, PRICE_TABLE["default"])
        return (self.input_tokens / 1_000_000) * inp + (self.output_tokens / 1_000_000) * out

    def to_dict(self) -> dict:
        data = asdict(self)
        data["cost_usd"] = round(self.cost(), 6)
        return data


class Telemetry:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else None
        self.records: list[Record] = []

    def record(self, kind: str, name: str, **fields) -> Record:
        entry = Record(kind=kind, name=name, **{
            k: v for k, v in fields.items() if k in Record.__dataclass_fields__
        })
        self.records.append(entry)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry.to_dict()) + "\n")
        return entry

    @contextmanager
    def timer(self, kind: str, name: str, **fields):
        started = time.monotonic()
        record = Record(kind=kind, name=name, **{
            k: v for k, v in fields.items() if k in Record.__dataclass_fields__
        })
        try:
            yield record
            record.ok = True
        except BaseException:
            record.ok = False
            raise
        finally:
            record.duration_ms = int((time.monotonic() - started) * 1000)
            self.records.append(record)
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record.to_dict()) + "\n")

    def summary(self) -> dict:
        total_cost = sum(r.cost() for r in self.records)
        total_ms = sum(r.duration_ms for r in self.records)
        by_kind: dict[str, dict] = {}
        for record in self.records:
            bucket = by_kind.setdefault(record.kind, {"count": 0, "ms": 0, "cost": 0.0, "failures": 0})
            bucket["count"] += 1
            bucket["ms"] += record.duration_ms
            bucket["cost"] += record.cost()
            bucket["failures"] += 0 if record.ok else 1
        return {
            "records": len(self.records),
            "total_cost_usd": round(total_cost, 6),
            "total_ms": total_ms,
            "failures": sum(1 for r in self.records if not r.ok),
            "by_kind": {k: {**v, "cost": round(v["cost"], 6)} for k, v in by_kind.items()},
        }

    def load(self) -> list[dict]:
        if not self.path or not self.path.is_file():
            return []
        entries = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return entries
