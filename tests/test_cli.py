#!/usr/bin/env python3
"""test_cli.py — интеграционные тесты CLI (spaces_verify.py)."""

import sys, os, json, tempfile, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.config import Config, Region
from src.snapshot import make_fixture


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    """Запустить spaces-verify как subprocess."""
    cmd = [sys.executable, "-m", "src.spaces_verify"]
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True)


class TestCLISmoke:
    def test_no_args_fails(self):
        """Без --image и --layers → exit code 2."""
        r = _run_cli("--config", "/dev/null")
        assert r.returncode == 2

    def test_bad_path_errors(self):
        """Несуществующий файл → exit code 2."""
        r = _run_cli("--image", "/nonexistent.bin")
        assert r.returncode == 2

    def test_empty_image_passes(self):
        """Пустой образ (все NOP) → PASS (exit 0)."""
        cfg = Config()
        data = make_fixture([], cfg.instr_bits, cfg.space_bytes)
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(data)
            path = f.name
        try:
            r = _run_cli("--image", path, "--format", "json")
            assert r.returncode == 0
            report = json.loads(r.stdout)
            assert report["overall_status"] == "PASS"
        finally:
            os.unlink(path)

    def test_oob_image_fails(self):
        """Инструкция с dst+ n > SPACE_BITS → FAIL (exit 1)."""
        cfg = Config()
        space_bits = cfg.space_bits
        # write instruction: copy(8, dst=space_bits-4, src=0) → out of bounds
        instrs = [(8, space_bits - 4, 0)]
        data = make_fixture(instrs, cfg.instr_bits, cfg.space_bytes)
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(data)
            path = f.name
        try:
            r = _run_cli("--image", path, "--format", "json")
            assert r.returncode == 1
            report = json.loads(r.stdout)
            assert report["overall_status"] == "FAIL"
            assert len(report["memory_check"]["violations"]) == 1
        finally:
            os.unlink(path)

    def test_l2_only_skips_memory_check(self):
        """--l2-only должен пропустить L1 (memory_check нет в отчёте)."""
        cfg = Config()
        data = make_fixture([], cfg.instr_bits, cfg.space_bytes)
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(data)
            path = f.name
        try:
            r = _run_cli("--image", path, "--format", "json", "--l2-only")
            assert r.returncode == 0
            report = json.loads(r.stdout)
            assert "memory_check" not in report
            assert "conflict_check" in report
        finally:
            os.unlink(path)

    def test_text_format_output(self):
        """--format text (default) выдаёт человекочитаемый отчёт."""
        cfg = Config()
        data = make_fixture([], cfg.instr_bits, cfg.space_bytes)
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(data)
            path = f.name
        try:
            r = _run_cli("--image", path)
            assert "L1" in r.stdout
            assert "OVERALL" in r.stdout
            assert r.returncode == 0
        finally:
            os.unlink(path)


class TestCLILayers:
    def test_no_conflict_layers(self):
        """Два слоя без конфликтов → PASS."""
        cfg = Config()
        layers = [
            make_fixture([(8, 65536, 0)], cfg.instr_bits, cfg.space_bytes),
            make_fixture([(8, 131072, 0)], cfg.instr_bits, cfg.space_bytes),
        ]
        paths = []
        for i, data in enumerate(layers):
            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(data)
                paths.append(f.name)
        try:
            r = _run_cli("--layers", *paths, "--format", "json")
            assert r.returncode == 0
            report = json.loads(r.stdout)
            assert report["overall_status"] == "PASS"
        finally:
            for p in paths:
                os.unlink(p)

    def test_conflict_layers_fails(self):
        """Два слота пишут в один dst → FAIL."""
        cfg = Config()
        layers = [
            make_fixture([(8, 100, 0), (8, 100, 1000)], cfg.instr_bits, cfg.space_bytes),
        ]
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(layers[0])
            path = f.name
        try:
            r = _run_cli("--image", path, "--format", "json")
            report = json.loads(r.stdout)
            assert report["overall_status"] == "FAIL"
            assert len(report["conflict_check"]["conflicts"]) >= 1
        finally:
            os.unlink(path)


class TestCLIWithConfig:
    def test_custom_config(self):
        """CLI с переданным JSON-конфигом."""
        cfg = Config()
        data = make_fixture([], cfg.instr_bits, cfg.space_bytes)
        config_data = {
            "space_bytes": cfg.space_bytes,
            "processor_n": cfg.processor_n,
            "protected_regions": [],
            "allowed_regions": [],
        }
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(data)
            img_path = f.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            cfg_path = f.name
        try:
            r = _run_cli("--image", img_path, "--config", cfg_path, "--format", "json")
            assert r.returncode == 0
        finally:
            os.unlink(img_path)
            os.unlink(cfg_path)
