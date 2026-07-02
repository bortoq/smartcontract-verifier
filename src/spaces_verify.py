#!/usr/bin/env python3
"""spaces-verify — L1+L2 верификатор образов адресного пространства.

Usage:
  # L1 + L2: проверить один образ
  spaces-verify --image layer.bin --config config.json

  # L1 + L2: проверить мульти-слойный образ
  spaces-verify --layers round_*.bin --config config.json

  # Только L2 (без memory-safety)
  spaces-verify --layers round_*.bin --config config.json --l2-only

  # JSON-вывод (CI-ready)
  spaces-verify --image layer.bin --config config.json --format json
"""

from __future__ import annotations
import argparse
import sys
import glob

from .config import Config
from .image_reader import ImageReader, Instruction
from .memory_check import MemoryChecker, MemoryCheckResult
from .conflict_check import ConflictChecker
from .report import ReportBuilder

__all__ = ["main"]


def _load_layer(path: str) -> bytes | None:
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


def _merge_memory_results(
    mem_checker: MemoryChecker,
    all_layers: list[list[Instruction]],
) -> MemoryCheckResult:
    """Прогнать L1 по всем слоям и объединить результаты."""
    all_violations = []
    total_checked = 0
    total_nop = 0
    status = "PASS"

    for tick, instrs in enumerate(all_layers):
        result = mem_checker.check_layer(instrs, tick)
        total_checked += result.total_checked
        total_nop += result.total_nop
        if result.status == "FAIL":
            status = "FAIL"
        all_violations.extend(result.violations)

    return MemoryCheckResult(status, all_violations, total_checked, total_nop)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="L1+L2 верификатор образов адресного пространства"
    )
    parser.add_argument("--image", type=str, default=None,
                        help="Путь к бинарному образу одного слоя")
    parser.add_argument("--layers", type=str, nargs="*", default=None,
                        help="Пути к образам нескольких слоёв (glob)")
    parser.add_argument("--config", type=str, default=None,
                        help="Путь к JSON-конфигу")
    parser.add_argument("--format", type=str, default="text",
                        choices=["text", "json"],
                        help="Формат вывода")
    parser.add_argument("--l2-only", action="store_true",
                        help="Только L2 (без memory-safety)")

    args = parser.parse_args()

    if not args.image and not args.layers:
        parser.error("укажите --image или --layers")

    cfg = Config(args.config)
    reader = ImageReader(cfg)
    mem_checker = MemoryChecker(cfg) if not args.l2_only else None

    # Загрузка слоёв
    layers_data: list[bytes] = []
    if args.image:
        data = _load_layer(args.image)
        if data is None:
            print(f"ERROR: file not found: {args.image}", file=sys.stderr)
            return 2
        layers_data.append(data)
    if args.layers:
        for pattern in args.layers:
            for path in sorted(glob.glob(pattern)):
                data = _load_layer(path)
                if data is None:
                    print(f"ERROR: file not found: {path}", file=sys.stderr)
                    return 2
                layers_data.append(data)

    if not layers_data:
        print("ERROR: no layer files found", file=sys.stderr)
        return 2

    # Парсинг (единая ветка — мёртвый код удалён)
    all_layers = [reader.read(data, tick) for tick, data in enumerate(layers_data)]

    # L1
    mem_result = None
    if not args.l2_only and mem_checker is not None:
        mem_result = _merge_memory_results(mem_checker, all_layers)

    # L2
    conflict_result = ConflictChecker.check_layers(all_layers)

    # Отчёт
    report = ReportBuilder(memory_result=mem_result, conflict_result=conflict_result)

    if args.format == "json":
        print(report.to_json())
    else:
        print(report.to_text())

    return 0 if report.overall_status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
