"""memory_check.py — L1: memory-safety проверки."""

from __future__ import annotations
from typing import NamedTuple
from .config import Config
from .image_reader import Instruction


class Violation(NamedTuple):
    tick: int
    slot: int
    n: int
    dst: int
    src: int
    reason: str


class MemoryCheckResult(NamedTuple):
    status: str           # "PASS" | "FAIL"
    violations: list[Violation]
    total_checked: int
    total_nop: int


class MemoryChecker:
    """Проверяет memory-safety для одного или нескольких слоёв."""

    def __init__(self, config: Config):
        self.cfg = config

    def check_layer(self, instrs: list[Instruction], tick: int = 0) -> MemoryCheckResult:
        """Проверить один слой (tick)."""
        violations: list[Violation] = []
        total = 0
        nop = 0

        for ins in instrs:
            total += 1
            if ins.is_nop():
                nop += 1
                continue

            # L1.4.1: boundary check
            if ins.dst + ins.n > self.cfg.space_bits:
                violations.append(Violation(
                    tick, ins.slot, ins.n, ins.dst, ins.src,
                    f"dst+ n = {ins.dst}+{ins.n} = {ins.dst + ins.n} > SPACE_BITS={self.cfg.space_bits}"
                ))
                continue

            # L1.4.2: protected region check
            for region in self.cfg.protected_regions:
                if region.intersects(ins.dst, ins.n):
                    violations.append(Violation(
                        tick, ins.slot, ins.n, ins.dst, ins.src,
                        f"dst range [{ins.dst}, {ins.dst + ins.n}) "  # noqa
                        f"intersects protected region {region.name} [{region.begin}, {region.end})"
                    ))
                    break  # одно нарушение на инструкцию

            # L1.4.3: allowed region check (если регионы заданы)
            if self.cfg.allowed_regions and not self._is_in_allowed(ins.dst, ins.n):
                violations.append(Violation(
                    tick, ins.slot, ins.n, ins.dst, ins.src,
                    f"dst range [{ins.dst}, {ins.dst + ins.n}) "  # noqa
                    f"is not within any allowed region"
                ))

        if violations:
            status = "FAIL"
        else:
            status = "PASS"

        return MemoryCheckResult(status, violations, total, nop)

    def _is_in_allowed(self, addr: int, n: int) -> bool:
        for region in self.cfg.allowed_regions:
            if region.contains(addr, n):
                return True
        return False
