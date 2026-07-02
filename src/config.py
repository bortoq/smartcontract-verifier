"""config.py — конфигурация защищённых и разрешённых регионов.

Регионы должны быть заданы явно (begin, end) в JSON-конфиге.
_resolve только вычисляет addr_bits, если он не указан.
Никакой автоматической подстановки границ по именам регионов.
"""

from __future__ import annotations
import json
import math

__all__ = [
    "Region",
    "Config",
    "derive_addr_bits",
]


def derive_addr_bits(space_bits: int) -> int:
    """Вычислить addr_bits как round8(ceil(log2(space_bits)))."""
    if space_bits <= 0:
        return 8
    raw = math.ceil(math.log2(space_bits))
    addr_bits = ((raw + 7) // 8) * 8
    if addr_bits < 8:
        addr_bits = 8
    return addr_bits


class Region:
    """Бит-адресуемый полуинтервал [begin, end)."""

    def __init__(self, name: str, begin: int | None, end: int | None):
        self.name = name
        self.begin = begin
        self.end = end

    def contains(self, addr: int, n: int) -> bool:
        """Проверяет, входит ли [addr, addr+n) целиком в регион."""
        if self.begin is None or self.end is None:
            return False
        if addr < self.begin:
            return False
        if addr + n > self.end:
            return False
        return True

    def intersects(self, addr: int, n: int) -> bool:
        """Проверяет пересечение [addr, addr+n) с регионом."""
        if self.begin is None or self.end is None:
            return False
        if addr + n <= self.begin:
            return False
        if addr >= self.end:
            return False
        return True

    def __repr__(self) -> str:
        return f"Region({self.name}, [{self.begin}, {self.end}))"


class Config:
    """Конфигурация пространства и регионов.

    Параметры:
      space_bytes: размер пространства в байтах (default 512 KiB)
      processor_n: количество слотов процессора (default 64)
      addr_bits: ширина адреса в битах (auto если None)
      protected_regions: список Region — запрещённые для записи зоны
      allowed_regions: список Region — разрешённые для записи зоны

    Все границы регионов должны быть заданы явно в JSON-конфиге.
    _resolve не подставляет границы автоматически.
    """

    def __init__(self, path: str | None = None):
        self.space_bytes: int = 524288
        self.processor_n: int = 64
        self.addr_bits: int | None = None
        self.protected_regions: list[Region] = []
        self.allowed_regions: list[Region] = []

        if path:
            self._load(path)

        self._resolve()

    def _load(self, path: str) -> None:
        with open(path) as f:
            d = json.load(f)

        self.space_bytes = d.get("space_bytes", self.space_bytes)
        self.processor_n = d.get("processor_n", self.processor_n)
        self.addr_bits = d.get("addr_bits")

        for r in d.get("protected_regions", []):
            self.protected_regions.append(
                Region(r["name"], r.get("begin"), r.get("end"))
            )

        for r in d.get("allowed_regions", []):
            self.allowed_regions.append(
                Region(r["name"], r.get("begin"), r.get("end"))
            )

    def _resolve(self) -> None:
        """Вычислить addr_bits, если не указан.

        Границы регионов НЕ подставляются — должны быть явными.
        """
        if self.addr_bits is None:
            self.addr_bits = derive_addr_bits(self.space_bytes * 8)

    @property
    def space_bits(self) -> int:
        return self.space_bytes * 8

    @property
    def instr_bits(self) -> int:
        return 3 * self.addr_bits

    @property
    def n_bits(self) -> int:
        return self.addr_bits

    @property
    def off_n(self) -> int:
        return 0

    @property
    def off_dst(self) -> int:
        return self.n_bits

    @property
    def off_src(self) -> int:
        return self.n_bits + self.addr_bits
