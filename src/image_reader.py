#!/usr/bin/env python3
"""image_reader.py — парсинг инструкций из бинарного образа пространства."""

from __future__ import annotations
from typing import Iterator
from .config import Config


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

        instrs = []
        for slot in range(self.cfg.processor_n):
            ins = self._read_instruction(data, slot)
            instrs.append(ins)
        return instrs

    def read_non_nop(self, data: bytes, tick: int = 0) -> list[Instruction]:
        """Прочитать только не-NOP инструкции."""
        return [i for i in self.read(data, tick) if not i.is_nop()]

    def _read_instruction(self, data: bytes, slot: int) -> Instruction:
        cfg = self.cfg
        bit_offset = slot * cfg.instr_bits
        byte_offset = bit_offset // 8

        if byte_offset + (cfg.instr_bits // 8) + 1 > len(data):
            return Instruction(slot, 0, 0, 0)

        n = self._read_bits(data, byte_offset, bit_offset % 8 + cfg.off_n, cfg.n_bits)
        dst = self._read_bits(data, byte_offset, bit_offset % 8 + cfg.off_dst, cfg.addr_bits)
        src = self._read_bits(data, byte_offset, bit_offset % 8 + cfg.off_src, cfg.addr_bits)
        return Instruction(slot, n, dst, src)

    @staticmethod
    def _read_bits(data: bytes, base_byte: int, bit_off: int, width: int) -> int:
        """Читает width бит из data, MSB-first."""
        if width == 0:
            return 0
        result = 0
        start_bit = base_byte * 8 + bit_off
        for i in range(width):
            byte_idx = (start_bit + i) >> 3
            bit_idx = 7 - ((start_bit + i) & 7)
            if byte_idx < len(data):
                bit = (data[byte_idx] >> bit_idx) & 1
                result = (result << 1) | bit
            else:
                result = result << 1
        return result
