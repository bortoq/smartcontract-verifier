#!/usr/bin/env python3
"""test_config.py — тесты config.py (граничные случаи)."""

import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.config import Config, Region, derive_addr_bits


class TestDeriveAddrBits:
    def test_small_space(self):
        assert derive_addr_bits(256) == 8    # 2^8 = 256

    def test_512kib(self):
        bits = 512 * 1024 * 8  # 4194304
        assert derive_addr_bits(bits) == 24  # ceil(log2)=22, round8=24

    def test_zero(self):
        assert derive_addr_bits(0) == 8

    def test_one(self):
        assert derive_addr_bits(1) == 8

    def test_exact_power_of_two(self):
        assert derive_addr_bits(256) == 8     # 2^8
        assert derive_addr_bits(65536) == 16  # 2^16


class TestConfigDefaults:
    def test_default_space_bytes(self):
        cfg = Config()
        assert cfg.space_bytes == 524288
        assert cfg.processor_n == 64
        assert cfg.addr_bits == 24

    def test_default_resolve(self):
        cfg = Config()
        assert cfg.space_bits == 524288 * 8
        assert cfg.instr_bits == 3 * 24
        assert cfg.n_bits == 24
        assert cfg.off_n == 0
        assert cfg.off_dst == 24
        assert cfg.off_src == 48

    def test_no_regions_by_default(self):
        cfg = Config()
        assert cfg.protected_regions == []
        assert cfg.allowed_regions == []


class TestConfigLoad:
    def test_load_full_config(self):
        data = {
            "space_bytes": 1024,
            "processor_n": 16,
            "addr_bits": 16,
            "protected_regions": [
                {"name": "CODE", "begin": 0, "end": 512}
            ],
            "allowed_regions": [
                {"name": "HEAP", "begin": 768, "end": 8192}
            ],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            cfg = Config(path)
            assert cfg.space_bytes == 1024
            assert cfg.processor_n == 16
            assert cfg.addr_bits == 16
            assert len(cfg.protected_regions) == 1
            assert cfg.protected_regions[0].name == "CODE"
            assert cfg.protected_regions[0].begin == 0
            assert cfg.protected_regions[0].end == 512
            assert len(cfg.allowed_regions) == 1
            assert cfg.allowed_regions[0].name == "HEAP"
        finally:
            os.unlink(path)

    def test_load_partial_config(self):
        data = {"space_bytes": 2048}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            cfg = Config(path)
            assert cfg.space_bytes == 2048
            assert cfg.processor_n == 64  # default
            assert cfg.addr_bits == derive_addr_bits(2048 * 8)
        finally:
            os.unlink(path)

    def test_load_null_addr_bits(self):
        data = {"addr_bits": None}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            cfg = Config(path)
            assert cfg.addr_bits == 24  # auto-derived from 512KiB
        finally:
            os.unlink(path)


class TestRegion:
    def test_contains(self):
        r = Region("test", 100, 200)
        assert r.contains(100, 50) is True
        assert r.contains(150, 50) is True
        assert r.contains(50, 50) is False  # addr < begin
        assert r.contains(100, 101) is False  # addr+n > end

    def test_contains_null_bounds(self):
        r = Region("none", None, None)
        assert r.contains(0, 100) is False  # невалидно

    def test_intersects(self):
        r = Region("test", 100, 200)
        assert r.intersects(150, 10) is True   # полностью внутри
        assert r.intersects(50, 60) is True    # [50,110) ∩ [100,200) = [100,110)
        assert r.intersects(50, 50) is False   # [50,100) не пересекает [100,200)
        assert r.intersects(200, 10) is False  # [200,210) не пересекает [100,200)

    def test_intersects_null_bounds(self):
        r = Region("none", None, None)
        assert r.intersects(0, 100) is False

    def test_len_end_before_begin(self):
        """Регион с end < begin — некорректен, но не падает."""
        r = Region("bad", 200, 100)
        assert r.contains(150, 10) is False
        assert r.intersects(150, 10) is False


class TestConfigRegionsNoAutoResolve:
    """Регионы с null-границами больше не резолвятся автоматически."""

    def test_null_begin_stays_none(self):
        cfg = Config()
        cfg.protected_regions = [Region("X", None, 100)]
        cfg._resolve()
        assert cfg.protected_regions[0].begin is None

    def test_null_end_stays_none(self):
        cfg = Config()
        cfg.protected_regions = [Region("X", 0, None)]
        cfg._resolve()
        assert cfg.protected_regions[0].end is None

    def test_intersects_with_none_returns_false(self):
        r = Region("X", None, 100)
        assert r.intersects(0, 10) is False
