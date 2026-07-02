#!/usr/bin/env python3
"""test_memory_check.py — тесты L1 memory-safety."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest
from src.config import Config, Region
from src.image_reader import Instruction
from src.memory_check import MemoryChecker

class TestMemoryChecker:
    def setup_method(self):
        self.cfg = Config()
        instr_bits = 3 * self.cfg.addr_bits
        self.processor_bits = self.cfg.processor_n * instr_bits
        self.mmio_end = self.processor_bits + 512
        self.cfg.protected_regions = [
            Region("PROCESSOR", 0, self.processor_bits),
            Region("MMIO", self.processor_bits, self.mmio_end),
        ]
        self.cfg.allowed_regions = [
            Region("TESTSCR", 65536, 131072),
        ]
        self.checker = MemoryChecker(self.cfg)

    def test_all_nop(self):
        r = self.checker.check_layer([Instruction(i,0,0,0) for i in range(64)])
        assert r.status == "PASS"

    def test_valid_write(self):
        r = self.checker.check_layer([Instruction(0,8,65536,0)])
        assert r.status == "PASS"

    def test_out_of_bounds(self):
        r = self.checker.check_layer([Instruction(0,8,self.cfg.space_bits-4,0)])
        assert r.status == "FAIL"

    def test_write_to_processor(self):
        r = self.checker.check_layer([Instruction(0,8,0,0)])
        assert r.status == "FAIL"
        assert any("PROCESSOR" in v.reason for v in r.violations)

    def test_write_to_mmio(self):
        """dst чуть выше PROCESSOR — MMIO."""
        dst = self.processor_bits + 8
        r = self.checker.check_layer([Instruction(0,8,dst,0)])
        assert r.status == "FAIL"
        assert any("MMIO" in v.reason for v in r.violations)

    def test_write_outside_allowed(self):
        """dst вне всех allowed-регионов."""
        r = self.checker.check_layer([Instruction(0,8,200000,0)])
        assert r.status == "FAIL"

    def test_no_allowed_regions_skip_check(self):
        self.cfg.allowed_regions = []
        r = self.checker.check_layer([Instruction(0,8,200000,0)])
        assert r.status == "PASS"


if __name__ == "__main__":
    pytest.main([__file__])
