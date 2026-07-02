# space-verifier — L1+L2 верификатор для copy-space/DPF

Верификатор **memory-safety** (L1) и **strict conflict-free scheduler** (L2) для образов адресного пространства copy-space/DPF.

**Основание**: формальная спецификация DDAS Address Space Contract v1
(`/home/user/work/ddas/doc/address_space_contract_v1.md`).

## Установка

```bash
pip install -e .
```

## Использование

```bash
# L1 + L2: проверить мульти-слойный образ
spaces-verify --layers tests/fixtures/layer_*.bin --config config/default_config.json

# L1 + L2 с JSON-выводом
spaces-verify --layers tests/fixtures/layer_*.bin --config config/default_config.json --format json

# Только L2 (пропустить memory-safety)
spaces-verify --layers tests/fixtures/layer_*.bin --config config/default_config.json --l2-only
```

Exit codes: 0 = PASS, 1 = FAIL, 2 = ошибка.

## Тесты

```bash
make test        # все тесты, verbose
make test-quick  # краткий вывод
```

## Структура

```
src/
  spaces_verify.py   # точка входа (CLI)
  image_reader.py    # парсинг инструкций из бинарного образа
  config.py          # конфигурация защищённых/разрешённых регионов
  memory_check.py    # L1: memory-safety (boundary, protected, allowed)
  conflict_check.py  # L2: strict non-overlap (DDAS Contract v1)
  snapshot.py        # save/load состояния пространства, генерация фикстур
  report.py          # отчёты (JSON + human-readable)
tests/
  test_conflict_check.py
  test_image_reader.py
  test_memory_check.py
  fixtures/
```

## Спецификация L2 (Strict Non-Overlap)

Заимствована из `ddas/src/core/strict_validator.c` (56 строк C).

Инвариант (DDAS Contract v1 §3):
> In a single Tick, no bit position may belong to more than one
> half-open interval participating in copy operations.

Проверяются: src∩src, dst∩dst, src∩dst (cross), self-overlap.
Сложность: O(K log K) на tick.

## Ссылки

- [DDAS: strict_validator.c](https://github.com/ddas/ddas) — исходный алгоритм
- [copy-space](https://github.com/copy-space) — базовая VM
- [DPF](https://github.com/DPF) — Forth0-совместимый процессор
