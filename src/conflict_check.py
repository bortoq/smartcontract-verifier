"""conflict_check.py — L2: Strict Non-Overlap Validator (DDAS Contract v1).

Алгоритм заимствован из DDAS strict_validator.c (56 строк C).
Спецификация: ddas/doc/address_space_contract_v1.md (п. 3 — Strict Non-Overlap Invariant).

Для каждого tick:
  1. Каждая не-NOP инструкция порождает ДВА полуинтервала: [src, src+n) и [dst, dst+n).
  2. Проверка self-overlap: src ∩ dst одной инструкции — недопустимо.
  3. Все полуинтервалы собираются, сортируются по start.
  4. Scan-line: если interval[i].start < interval[i-1].end → overlap → FAIL.
"""

from __future__ import annotations
from typing import NamedTuple
from .image_reader import Instruction


class OverlapKind:
    """Тип пересечения для диагностики."""
    SELF_SRC_DST = "self-src-dst"        # src и dst одной инструкции
    SRC_SRC = "src-src"                  # src двух разных инструкций
    DST_DST = "dst-dst"                  # dst двух разных инструкций
    SRC_DST = "src-dst"                  # src одной ∩ dst другой (cross)
    DST_SRC = "dst-src"                  # dst одной ∩ src другой (cross)


class Conflict(NamedTuple):
    tick: int
    slot_a: int
    slot_b: int
    overlap_begin: int
    overlap_end: int
    kind: str                          # OverlapKind


class _Interval(NamedTuple):
    """Внутренний интервал для scan-line."""
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
    """Проверяет full strict non-overlap в каждом tick.

    Инвариант (DDAS Contract v1 §3):
      "In a single Tick, no bit position may belong to more than one
       half-open interval participating in copy operations."

    Это означает, что для каждого tick:
      - src ∩ dst одной инструкции — недопустимо (self-overlap).
      - src_i ∩ src_j — недопустимо.
      - dst_i ∩ dst_j — недопустимо.
      - src_i ∩ dst_j — недопустимо.
    """

    @staticmethod
    def check_layers(layers: list[list[Instruction]]) -> ConflictCheckResult:
        """Проверить последовательность слоёв на конфликты."""
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
        """Проверить один tick на full strict non-overlap (O(K log K))."""
        conflicts: list[Conflict] = []
        intervals: list[_Interval] = []

        for ins in instrs:
            if ins.is_nop():
                continue

            n, dst, src = ins.n, ins.dst, ins.src

            # ── Self-overlap check: [src, src+n) ∩ [dst, dst+n) ──
            src_end = src + n
            dst_end = dst + n
            if not (src_end <= dst or dst_end <= src):
                # self-overlap: src и dst одной инструкции пересекаются
                overlap_begin = max(src, dst)
                overlap_end = min(src_end, dst_end)
                conflicts.append(Conflict(
                    tick, ins.slot, ins.slot,
                    overlap_begin, overlap_end,
                    OverlapKind.SELF_SRC_DST,
                ))
                # Продолжаем: добавляем оба интервала, scan-line тоже их поймает
                # Но мы уже записали конфликт, так что можно не дублировать
                # Всё равно добавляем для scan-line консистентности

            # ── Добавляем src и dst интервалы ──
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
                # Overlap detected
                overlap_begin = curr.start
                overlap_end = min(curr.end, prev.end)

                # Определяем тип пересечения
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

    # ── Опциональный batch (для совместимости с DDAS C API) ──

    @staticmethod
    def check_batch(ops: list[tuple[int, int, int]], tick: int = 0) -> list[Conflict]:
        """Проверить batch операций (n, dst, src) на strict non-overlap.

        Удобно для тестов — не требует полного образа.
        """
        instrs = [Instruction(i, n, dst, src) for i, (n, dst, src) in enumerate(ops)]
        return ConflictChecker._check_tick(instrs, tick)
