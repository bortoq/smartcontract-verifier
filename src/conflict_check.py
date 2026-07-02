"""conflict_check.py — L2: Strict Non-Overlap Validator.

Formal invariant (see README.md for full specification):

  In a single execution round, no bit position may belong to more than one
  half-open interval participating in copy operations.

  Therefore:
    - Any instruction whose source and destination overlap is invalid.
    - Any two instructions overlapping in any position are invalid.

Algorithm (O(K log K) per round):
  1. Each non-NOP instruction generates TWO intervals: [src, src+n) and [dst, dst+n).
  2. Check self-overlap: src ∩ dst of the same instruction is invalid.
  3. Collect all intervals, sort by start.
  4. Scan-line: if interval[i].start < interval[i-1].end → conflict.
"""

from __future__ import annotations
from typing import NamedTuple
from .image_reader import Instruction


class OverlapKind:
    """Conflict type for diagnostic output."""
    SELF_SRC_DST = "self-src-dst"        # src and dst of the same instruction
    SRC_SRC = "src-src"                  # src of two different instructions
    DST_DST = "dst-dst"                  # dst of two different instructions
    SRC_DST = "src-dst"                  # src of A overlaps dst of B (cross)
    DST_SRC = "dst-src"                  # dst of A overlaps src of B (cross)


class Conflict(NamedTuple):
    tick: int
    slot_a: int
    slot_b: int
    overlap_begin: int
    overlap_end: int
    kind: str                          # OverlapKind


class _Interval(NamedTuple):
    """Internal interval for scan-line sort."""
    start: int
    end: int
    slot: int
    origin: str                        # "src" | "dst"


class ConflictCheckResult(NamedTuple):
    status: str                        # "PASS" | "FAIL"
    conflicts: list[Conflict]
    layers_checked: int
    total_non_nop: int


class ConflictChecker:
    """Verify strict non-overlap within each execution round.

    The invariant guarantees deterministic, race-free parallel execution:
    no bit position belongs to more than one source or destination interval
    across all contracts in the same round.
    """

    @staticmethod
    def check_layers(layers: list[list[Instruction]]) -> ConflictCheckResult:
        """Check a sequence of execution rounds for conflicts."""
        all_conflicts: list[Conflict] = []
        total_non_nop = 0

        for tick, instrs in enumerate(layers):
            conflicts = ConflictChecker._check_tick(instrs, tick)
            all_conflicts.extend(conflicts)
            total_non_nop += sum(1 for i in instrs if not i.is_nop())

        status = "FAIL" if all_conflicts else "PASS"
        return ConflictCheckResult(status, all_conflicts, len(layers), total_non_nop)

    @staticmethod
    def _check_tick(instrs: list[Instruction], tick: int) -> list[Conflict]:
        """Check a single round for strict non-overlap (O(K log K))."""
        conflicts: list[Conflict] = []
        intervals: list[_Interval] = []

        for ins in instrs:
            if ins.is_nop():
                continue

            n, dst, src = ins.n, ins.dst, ins.src

            # ── Self-overlap: [src, src+n) ∩ [dst, dst+n) ──
            src_end = src + n
            dst_end = dst + n
            if not (src_end <= dst or dst_end <= src):
                overlap_begin = max(src, dst)
                overlap_end = min(src_end, dst_end)
                conflicts.append(Conflict(
                    tick, ins.slot, ins.slot,
                    overlap_begin, overlap_end,
                    OverlapKind.SELF_SRC_DST,
                ))

            # ── Add src and dst intervals ──
            intervals.append(_Interval(src, src_end, ins.slot, "src"))
            intervals.append(_Interval(dst, dst_end, ins.slot, "dst"))

        if not intervals:
            return conflicts

        # ── Sort by start, then by end ──
        intervals.sort(key=lambda x: (x.start, x.end))

        # ── Scan-line ──
        for i in range(1, len(intervals)):
            prev = intervals[i - 1]
            curr = intervals[i]

            if curr.start < prev.end:
                overlap_begin = curr.start
                overlap_end = min(curr.end, prev.end)

                if prev.slot == curr.slot:
                    kind = OverlapKind.SELF_SRC_DST
                elif prev.origin == "src" and curr.origin == "src":
                    kind = OverlapKind.SRC_SRC
                elif prev.origin == "dst" and curr.origin == "dst":
                    kind = OverlapKind.DST_DST
                elif prev.origin == "src" and curr.origin == "dst":
                    kind = OverlapKind.SRC_DST
                else:
                    kind = OverlapKind.DST_SRC

                conflicts.append(Conflict(
                    tick, prev.slot, curr.slot,
                    overlap_begin, overlap_end,
                    kind,
                ))

        return conflicts

    @staticmethod
    def check_batch(ops: list[tuple[int, int, int]], tick: int = 0) -> list[Conflict]:
        """Check a batch of operations (n, dst, src) for strict non-overlap.

        Convenient for testing — doesn't require a full memory image.
        """
        instrs = [Instruction(i, n, dst, src) for i, (n, dst, src) in enumerate(ops)]
        return ConflictChecker._check_tick(instrs, tick)
