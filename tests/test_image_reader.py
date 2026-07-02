#!/usr/bin/env python3
"""test_image_reader.py — тесты парсинга инструкций."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import struct
import pytest
from src.config import Config
from src.image_reader import ImageReader, Instruction


def _make_space(config: Config, instructions: list) -> bytes:
    """Создать бинарный образ с заданными инструкциями."""
    size_bytes = config.space_bytes
    data = bytearray(size_bytes)

    for slot, n, dst, src in instructions:
        bit_offset = slot * config.instr_bits
        byte_off = bit_offset // 8
        bit_off_in_byte = bit_offset % 8

        def write_bits(val: int, off: int, width: int):
            start_bit = byte_off * 8 + bit_off_in_byte + off
            for i in range(width):
                bit = (val >> (width - 1 - i)) & 1
                byte_idx = (start_bit + i) >> 3
                bit_idx = 7 - ((start_bit + i) & 7)
                if bit:
                    data[byte_idx] |= (1 << bit_idx)
                else:
                    data[byte_idx] &= ~(1 << bit_idx)

        write_bits(n, config.off_n, config.n_bits)
        write_bits(dst, config.off_dst, config.addr_bits)
        write_bits(src, config.off_src, config.addr_bits)

    return bytes(data)


class TestImageReader:
    def setup_method(self):
        self.cfg = Config()
        self.reader = ImageReader(self.cfg)

    def test_empty_space(self):
        data = b"\x00" * self.cfg.space_bytes
        instrs = self.reader.read(data)
        assert len(instrs) == self.cfg.processor_n
        for ins in instrs:
            assert ins.is_nop()

    def test_single_instruction(self):
        data = _make_space(self.cfg, [(0, 8, 100, 200)])
        instrs = self.reader.read(data)
        assert instrs[0].n == 8
        assert instrs[0].dst == 100
        assert instrs[0].src == 200
        for ins in instrs[1:]:
            assert ins.is_nop()

    def test_multiple_instructions(self):
        data = _make_space(self.cfg, [
            (0, 8, 100, 200),
            (1, 16, 300, 400),
            (63, 1, 500, 600),
        ])
        instrs = self.reader.read(data)
        assert instrs[0].n == 8
        assert instrs[0].dst == 100
        assert instrs[0].src == 200
        assert instrs[1].n == 16
        assert instrs[1].dst == 300
        assert instrs[1].src == 400
        assert instrs[63].n == 1
        assert instrs[63].dst == 500
        assert instrs[63].src == 600


class TestInstruction:
    def test_is_nop(self):
        assert Instruction(0, 0, 0, 0).is_nop()
        assert not Instruction(0, 1, 0, 0).is_nop()

    def test_repr(self):
        r = repr(Instruction(5, 8, 100, 200))
        assert "slot=5" in r
        assert "copy(8" in r
        assert "dst=100" in r
        assert "src=200" in r


if __name__ == "__main__":
    pytest.main([__file__])
