#!/usr/bin/env python3
"""test_conflict_check.py — тесты L2 strict non-overlap (DDAS Contract v1)."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.image_reader import Instruction
from src.conflict_check import ConflictChecker, OverlapKind


class TestConflictChecker:
    def test_all_nop(self):
        """Все NOP → PASS."""
        layers = [
            [Instruction(i, 0, 0, 0) for i in range(64)],
        ]
        result = ConflictChecker.check_layers(layers)
        assert result.status == "PASS"
        assert len(result.conflicts) == 0

    def test_no_conflict_single_layer(self):
        """Два disjoint dst, disjoint src → PASS (нет пересечений)."""
        layers = [[
            Instruction(0, 8, 100, 0),       # src [0,8)  dst [100,108)
            Instruction(1, 8, 200, 1000),     # src [1000,1008) dst [200,208)
        ]]
        result = ConflictChecker.check_layers(layers)
        assert result.status == "PASS"

    def test_same_dst(self):
        """Два слота пишут в один dst → FAIL, disjoint src чтобы не плодить конфликты."""
        layers = [[
            Instruction(0, 8, 100, 0),         # src [0,8)
            Instruction(1, 8, 100, 1000),       # src [1000,1008) dst same → один dst-dst конфликт
        ]]
        result = ConflictChecker.check_layers(layers)
        assert result.status == "FAIL"
        assert len(result.conflicts) == 1
        c = result.conflicts[0]
        assert c.slot_a == 0
        assert c.slot_b == 1
        assert c.kind == OverlapKind.DST_DST
        assert c.overlap_begin == 100
        assert c.overlap_end == 108

    def test_partial_overlap(self):
        """Частичное перекрытие dst → FAIL, disjoint src."""
        layers = [[
            Instruction(0, 16, 100, 0),         # src [0,16)
            Instruction(1, 16, 110, 1000),       # src [1000,1016) dst [110,126)
                                                 # dst: [100,116) ∩ [110,126) = [110,116)
        ]]
        result = ConflictChecker.check_layers(layers)
        assert result.status == "FAIL"
        assert len(result.conflicts) == 1
        c = result.conflicts[0]
        assert c.kind == OverlapKind.DST_DST
        assert c.overlap_begin == 110
        assert c.overlap_end == 116

    def test_src_conflict_now_fails(self):
        """SRC-конфликт — FAIL (strict mode проверяет ВСЕ пересечения)."""
        layers = [[
            Instruction(0, 8, 100, 50),         # src [50,58)
            Instruction(1, 8, 200, 50),          # src [50,58) — same src → src∩src
        ]]
        result = ConflictChecker.check_layers(layers)
        assert result.status == "FAIL"
        assert len(result.conflicts) == 1
        c = result.conflicts[0]
        assert c.kind == OverlapKind.SRC_SRC
        assert c.overlap_begin == 50
        assert c.overlap_end == 58

    def test_self_overlap(self):
        """src и dst одной инструкции пересекаются → FAIL."""
        # copy(16, dst=100, src=110): [100,116) ∩ [110,126) = [110,116)
        layers = [[
            Instruction(0, 16, 100, 110),
        ]]
        result = ConflictChecker.check_layers(layers)
        assert result.status == "FAIL"
        assert len(result.conflicts) >= 1
        c = result.conflicts[0]
        assert c.kind in (OverlapKind.SELF_SRC_DST, OverlapKind.SRC_DST)
        assert c.slot_a == c.slot_b == 0

    def test_cross_overlap(self):
        """src слота A пересекает dst слота B → FAIL."""
        # slot0: copy(8, dst=100, src=200)   dst [100,108)
        # slot1: copy(8, dst=190, src=95)    src [95,103) overlaps dst [100,108)
        layers = [[
            Instruction(0, 8, 100, 200),
            Instruction(1, 8, 190, 95),
        ]]
        result = ConflictChecker.check_layers(layers)
        assert result.status == "FAIL"
        assert len(result.conflicts) >= 1
        # Actually [95,103) ∩ [100,108) = [100,103) — src of 1 overlaps dst of 0
        c = result.conflicts[0]
        assert c.kind in (OverlapKind.SRC_DST, OverlapKind.DST_SRC)

    def test_no_conflict_disjoint_all(self):
        """Всё disjoint: и src, и dst — PASS."""
        layers = [[
            Instruction(0, 8, 100, 0),
            Instruction(1, 8, 200, 300),
            Instruction(2, 8, 400, 500),
        ]]
        result = ConflictChecker.check_layers(layers)
        assert result.status == "PASS"

    def test_multiple_layers_no_conflict(self):
        """Разные слои — независимы, внутри каждого всё disjoint."""
        layers = [
            [Instruction(i, 8, i * 16 + 100, i * 16 + 1000) for i in range(10)],
            [Instruction(i, 8, i * 16 + 2000, i * 16 + 3000) for i in range(5)],
        ]
        result = ConflictChecker.check_layers(layers)
        assert result.status == "PASS"

    def test_different_layers_independent(self):
        """Конфликт есть только внутри layer 0, layer 1 чист → ровно 2 конфликта в layer 0."""
        layers = [
            [Instruction(0, 8, 100, 0),           # src [0,8)
             Instruction(1, 8, 100, 1000)],        # src [1000,1008) dst same → dst-dst
            [Instruction(0, 8, 100, 0),
             Instruction(1, 8, 200, 1000)],        # disjoint → no conflict
        ]
        result = ConflictChecker.check_layers(layers)
        assert result.status == "FAIL"
        assert len(result.conflicts) == 1
        assert result.conflicts[0].tick == 0

    # ── Batch API ──

    def test_batch_all_nop(self):
        """Все NOP → PASS."""
        conflicts = ConflictChecker.check_batch([(0, 0, 0), (0, 0, 0)])
        assert len(conflicts) == 0

    def test_batch_self_overlap(self):
        """Self-overlap через batch API."""
        conflicts = ConflictChecker.check_batch([(16, 100, 110)])
        assert len(conflicts) >= 1

    def test_batch_src_conflict(self):
        """Src конфликт через batch API."""
        conflicts = ConflictChecker.check_batch([(8, 100, 50), (8, 200, 50)])
        assert len(conflicts) >= 1
        assert conflicts[0].kind == OverlapKind.SRC_SRC
