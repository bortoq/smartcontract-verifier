"""report.py — форматирование отчётов."""

from __future__ import annotations
import json
from .memory_check import MemoryCheckResult, Violation
from .conflict_check import ConflictCheckResult, Conflict


def violations_to_dict(violations: list[Violation]) -> list[dict]:
    return [
        {
            "tick": v.tick,
            "slot": v.slot,
            "n": v.n,
            "dst": v.dst,
            "src": v.src,
            "reason": v.reason,
        }
        for v in violations
    ]


def conflicts_to_dict(conflicts: list[Conflict]) -> list[dict]:
    return [
        {
            "tick": c.tick,
            "slot_a": c.slot_a,
            "slot_b": c.slot_b,
            "overlap_begin": c.overlap_begin,
            "overlap_end": c.overlap_end,
            "kind": c.kind,
        }
        for c in conflicts
    ]


def _kind_label(kind: str) -> str:
    labels = {
        "self-src-dst": "self (src ∩ dst)",
        "src-src": "src ∩ src",
        "dst-dst": "dst ∩ dst",
        "src-dst": "src ∩ dst",
        "dst-src": "dst ∩ src",
    }
    return labels.get(kind, kind)


class ReportBuilder:
    def __init__(self, memory_result: MemoryCheckResult | None = None,
                 conflict_result: ConflictCheckResult | None = None):
        self.memory = memory_result
        self.conflict = conflict_result

    def to_json(self) -> str:
        d: dict = {}
        if self.memory:
            d["memory_check"] = {
                "status": self.memory.status,
                "violations": violations_to_dict(self.memory.violations),
                "total_checked": self.memory.total_checked,
                "total_nop": self.memory.total_nop,
            }
        if self.conflict:
            d["conflict_check"] = {
                "status": self.conflict.status,
                "layers_checked": self.conflict.layers_checked,
                "total_non_nop": self.conflict.total_non_nop,
                "conflicts": conflicts_to_dict(self.conflict.conflicts),
            }

        status = "PASS"
        if self.memory and self.memory.status == "FAIL":
            status = "FAIL"
        if self.conflict and self.conflict.status == "FAIL":
            status = "FAIL"
        d["overall_status"] = status

        return json.dumps(d, indent=2)

    def to_text(self) -> str:
        lines: list[str] = []

        if self.memory:
            lines.append("=" * 60)
            lines.append(f"  L1 Memory-Safety Check: {self.memory.status}")
            lines.append(f"  Instructions: {self.memory.total_checked} total, "
                         f"{self.memory.total_nop} NOP, "
                         f"{len(self.memory.violations)} violations")
            if self.memory.violations:
                for v in self.memory.violations:
                    lines.append(f"    ❌ tick={v.tick} slot={v.slot}: {v.reason}")
            else:
                lines.append("    ✅ No violations")

        if self.conflict:
            lines.append("=" * 60)
            lines.append(f"  L2 Conflict-Free Check: {self.conflict.status}")
            lines.append(f"  Layers: {self.conflict.layers_checked}, "
                         f"non-NOP: {self.conflict.total_non_nop}, "
                         f"conflicts: {len(self.conflict.conflicts)}")
            if self.conflict.conflicts:
                for c in self.conflict.conflicts:
                    kind_str = _kind_label(c.kind)
                    lines.append(
                        f"    ❌ tick={c.tick}: slot {c.slot_a} {kind_str} slot {c.slot_b} "
                        f"overlap [{c.overlap_begin}, {c.overlap_end})"
                    )
            else:
                lines.append("    ✅ No conflicts")

        lines.append("=" * 60)
        overall = "PASS" if all(
            (not self.memory or self.memory.status == "PASS") and
            (not self.conflict or self.conflict.status == "PASS")
        ) else "FAIL"
        lines.append(f"  OVERALL: {overall}")

        return "\n".join(lines)

    @property
    def overall_status(self) -> str:
        if self.memory and self.memory.status == "FAIL":
            return "FAIL"
        if self.conflict and self.conflict.status == "FAIL":
            return "FAIL"
        return "PASS"
