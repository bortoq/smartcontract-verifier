"""image_reader.py — парсинг инструкций из бинарного образа пространства.

_read_bits использует int.from_bytes + сдвиг/маску вместо побитового цикла.
"""

from __future__ import annotations
from .config import Config

__all__ = [
    "Instruction",
    "ImageReader",
]


class Instruction:
    """Одна инструкция copy(n, dst, src)."""

    def __init__(self, slot: int, n: int, dst: int, src: int):
        self.slot = slot
        self.n = n
        self.dst = dst
        self.src = src

    def is_nop(self) -> bool:
        return self.n == 0

    def __repr__(self) -> str:
        return f"slot={self.slot}: copy({self.n}, dst={self.dst}, src={self.src})"


class ImageReader:
    """Читает инструкции из дампа пространства."""

    def __init__(self, config: Config):
        self.cfg = config

    def read(self, data: bytes, tick: int = 0) -> list[Instruction]:
        """Прочитать все инструкции из бинарного дампа space."""
        if len(data) < self.cfg.space_bytes:
            raise ValueError(
                f"data size {len(data)} < space_bytes {self.cfg.space_bytes}"
            )

        return [
            self._read_instruction(data, slot)
            for slot in range(self.cfg.processor_n)
        ]

    def read_non_nop(self, data: bytes, tick: int = 0) -> list[Instruction]:
        """Прочитать только не-NOP инструкции."""
        return [i for i in self.read(data, tick) if not i.is_nop()]

    def _read_instruction(self, data: bytes, slot: int) -> Instruction:
        cfg = self.cfg
        start_bit = slot * cfg.instr_bits

        n = self._read_bits(data, start_bit + cfg.off_n, cfg.n_bits)
        dst = self._read_bits(data, start_bit + cfg.off_dst, cfg.addr_bits)
        src = self._read_bits(data, start_bit + cfg.off_src, cfg.addr_bits)
        return Instruction(slot, n, dst, src)

    @staticmethod
    def _read_bits(data: bytes, start_bit: int, width: int) -> int:
        """Извлечь width бит из data, начиная с start_bit (MSB-first).

        Использует int.from_bytes + сдвиг — O(1) по ширине.
        """
        if width <= 0:
            return 0
        if width > 64:
            # На случай >64 бит — падаем на побитовый (но в конфиге addr_bits ≤ 32)
            return ImageReader._read_bits_slow(data, start_bit, width)

        end_bit = start_bit + width
        start_byte = start_bit >> 3
        end_byte = (end_bit - 1) >> 3
        n_bytes = end_byte - start_byte + 1

        chunk = data[start_byte:start_byte + n_bytes]
        # big-endian: первый байт chunk — MSB
        val = int.from_bytes(chunk, 'big')

        # Отбросить лишние биты слева (MSB) и справа (LSB)
        # total bits в val = 8 * n_bytes
        # Позиция start_bit внутри val: (8 * n_bytes) - (start_bit & 7) - width
        shift = 8 * n_bytes - (start_bit & 7) - width
        if shift > 0:
            val >>= shift

        mask = (1 << width) - 1
        return val & mask

    @staticmethod
    def _read_bits_slow(data: bytes, start_bit: int, width: int) -> int:
        """Побитовый fallback (только для width > 64)."""
        result = 0
        for i in range(width):
            pos = start_bit + i
            byte_idx = pos >> 3
            bit_idx = 7 - (pos & 7)
            if byte_idx < len(data):
                bit = (data[byte_idx] >> bit_idx) & 1
                result = (result << 1) | bit
            else:
                result = result << 1
        return result
