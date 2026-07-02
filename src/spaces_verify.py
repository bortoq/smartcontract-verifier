#!/usr/bin/env python3
"""spaces-verify — L1+L2 верификатор образов адресного пространства.

Usage:
  # L1: проверить один слой
  spaces-verify check --image layer.bin --config config.json

  # L1 + L2: проверить мульти-слойный образ
  spaces-verify check --layers layer_*.bin --config config.json

  # L2: проверить последовательность слоёв на конфликты
  spaces-verify check --layers layer_*.bin --config config.json --l2-only

  # Вывод JSON
  spaces-verify check --image layer.bin --config config.json --format json
"""

from __future__ import annotations
import argparse
import sys
import glob

from .config import Config
from .image_reader import ImageReader
from .memory_check import MemoryChecker
from .conflict_check import ConflictChecker
from .report import ReportBuilder


def _load_layer(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


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
    mem_checker = MemoryChecker(cfg)

    layers_data: list[bytes] = []
    if args.image:
        layers_data.append(_load_layer(args.image))
    if args.layers:
        for pattern in args.layers:
            for path in sorted(glob.glob(pattern)):
                layers_data.append(_load_layer(path))

    if not layers_data:
        print("ERROR: no layer files found", file=sys.stderr)
        return 2

    # Парсинг
    all_layers: list = []
    for tick, data in enumerate(layers_data):
        if args.l2_only:
            instrs = reader.read(data, tick)
        else:
            instrs = reader.read(data, tick)
        all_layers.append(instrs)

    # L1
    mem_result = None
    if not args.l2_only:
        mem_results = []
        for tick, instrs in enumerate(all_layers):
            mem_results.append(mem_checker.check_layer(instrs, tick))

        # Объединяем результаты
        all_violations = []
        total = sum(r.total_checked for r in mem_results)
        nop = sum(r.total_nop for r in mem_results)
        status = "PASS"
        for r in mem_results:
            if r.status == "FAIL":
                status = "FAIL"
            all_violations.extend(r.violations)

        from .memory_check import MemoryCheckResult
        mem_result = MemoryCheckResult(status, all_violations, total, nop)

    # L2
    conflict_result = None
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
