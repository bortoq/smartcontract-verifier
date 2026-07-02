"""config.py — конфигурация защищённых и разрешённых регионов."""

from __future__ import annotations
import json
import math

def _derive_addr_bits(space_bits: int) -> int:
    raw = math.ceil(math.log2(space_bits))
    addr_bits = ((raw + 7) // 8) * 8
    if addr_bits < 8:
        addr_bits = 8
    return addr_bits


class Region:
    def __init__(self, name: str, begin: int | None, end: int | None):
        self.name = name
        self.begin = begin
        self.end = end

    def contains(self, addr: int, n: int) -> bool:
        """Проверяет, входит ли [addr, addr+n) в регион."""
        if self.begin is not None and addr < self.begin:
            return False
        if self.end is not None and addr + n > self.end:
            return False
        return True

    def intersects(self, addr: int, n: int) -> bool:
        """Проверяет пересечение [addr, addr+n) с регионом."""
        if self.begin is not None and addr + n <= self.begin:
            return False
        if self.end is not None and addr >= self.end:
            return False
        return True

    def __repr__(self) -> str:
        return f"Region({self.name}, [{self.begin}, {self.end}))"


class Config:
    def __init__(self, path: str | None = None):
        self.space_bytes: int = 524288       # 512 KiB
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
            self.protected_regions.append(Region(r["name"], r.get("begin"), r.get("end")))

        for r in d.get("allowed_regions", []):
            self.allowed_regions.append(Region(r["name"], r.get("begin"), r.get("end")))

    def _resolve(self) -> None:
        """Вычислить динамические размеры и подставить addr_bits."""
        space_bits = self.space_bytes * 8

        if self.addr_bits is None:
            self.addr_bits = _derive_addr_bits(space_bits)

        n_bits = self.addr_bits
        instr_bits = 3 * self.addr_bits
        processor_bits = self.processor_n * instr_bits

        # Разрешить защищённые регионы с null-границами
        for r in self.protected_regions:
            if r.name == "PROCESSOR" and r.begin is None:
                r.begin = 0
            if r.name == "PROCESSOR" and r.end is None:
                r.end = processor_bits
            if r.name == "MMIO" and r.begin is None:
                r.begin = processor_bits
            if r.name == "MMIO" and r.end is None:
                # MMIO заканчивается на следующей байтовой границе
                mmio_bit_size = 4 + 4 * n_bits  # REQ/DONE/EOF/ERR + ADDR/LEN/GOT для IN и OUT
                r.end = ((processor_bits + mmio_bit_size + 7) // 8) * 8

        # Разрешить allowed-регионы
        for r in self.allowed_regions:
            if r.name == "TESTSCR" and r.begin is None:
                r.begin = 0  # будет переопределён, если ART найден
                r.end = space_bits

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
