#!/usr/bin/env python3
"""test_integration.py — интеграционные тесты с реальными бинарными образами.

Использует фикстуры из tests/fixtures/*.bin
"""

import sys, os, json, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-m", "src.spaces_verify"]
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True)


class TestIntegrationFixtures:
    def test_sample_passes(self):
        """sample.bin проходит L1 + L2 (все инструкции корректны)."""
        path = os.path.join(FIXTURES_DIR, "sample.bin")
        assert os.path.exists(path)
        r = _run_cli("--image", path, "--format", "json")
        assert r.returncode == 0, f"FAIL: {r.stderr}"
        report = json.loads(r.stdout)
        assert report["overall_status"] == "PASS"

    def test_oob_fails(self):
        """oob_dst.bin нарушает boundary → FAIL."""
        path = os.path.join(FIXTURES_DIR, "oob_dst.bin")
        assert os.path.exists(path)
        r = _run_cli("--image", path, "--format", "json")
        assert r.returncode == 1
        report = json.loads(r.stdout)
        assert report["overall_status"] == "FAIL"
        assert len(report["memory_check"]["violations"]) >= 1
        assert "SPACE_BITS" in report["memory_check"]["violations"][0]["reason"]

    def test_layer_conflict_fails(self):
        """layer_conflict.bin имеет конфликт записи → FAIL."""
        path = os.path.join(FIXTURES_DIR, "layer_conflict.bin")
        assert os.path.exists(path)
        r = _run_cli("--image", path, "--format", "json")
        assert r.returncode == 1
        report = json.loads(r.stdout)
        assert report["overall_status"] == "FAIL"
        assert len(report["conflict_check"]["conflicts"]) >= 1

    def test_multi_layer_no_conflict(self):
        """Два sample-образа как разные слои → PASS (нет cross-layer конфликтов)."""
        path1 = os.path.join(FIXTURES_DIR, "sample.bin")
        path2 = os.path.join(FIXTURES_DIR, "sample.bin")
        r = _run_cli("--layers", path1, path2, "--format", "json")
        assert r.returncode == 0
        report = json.loads(r.stdout)
        assert report["overall_status"] == "PASS"

    def test_l2_only_on_sample(self):
        """--l2-only на корректном образе → PASS, без memory_check."""
        path = os.path.join(FIXTURES_DIR, "sample.bin")
        r = _run_cli("--image", path, "--format", "json", "--l2-only")
        assert r.returncode == 0
        report = json.loads(r.stdout)
        assert "memory_check" not in report
        assert report["conflict_check"]["status"] == "PASS"

    def test_json_output_format(self):
        """Проверка структуры JSON-вывода."""
        path = os.path.join(FIXTURES_DIR, "sample.bin")
        r = _run_cli("--image", path, "--format", "json")
        report = json.loads(r.stdout)
        assert "overall_status" in report
        assert "memory_check" in report
        assert "conflict_check" in report
        assert isinstance(report["memory_check"]["violations"], list)
        assert isinstance(report["conflict_check"]["conflicts"], list)
