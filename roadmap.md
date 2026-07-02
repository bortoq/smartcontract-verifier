# Roadmap: L1+L2 Verifier для copy-space/DPF

**Репозиторий**: `/home/user/work/smartcontract-verifier/`
**Цель**: верификатор memory-safety (L1) + strict conflict-free scheduler (L2) для образов пространства.
**Основание**: документировано в `doc/roadmap.md` (п. 1-2) — проверка согласованности пространства.

---

## Статус

| Компонент | Статус | Примечание |
|---|---|---|
| L1: Memory-Safety Checker | ✅ Реализован | boundary + protected + allowed regions |
| L2: Conflict-Free Checker (strict) | ✅ Реализован | DDAS Contract v1 full strict non-overlap |
| Snapshot utility | ✅ Реализован | save/load тестовых фикстур |
| CLI `spaces-verify` | ✅ Реализован | L1+L2, JSON/text, CI-ready exit codes |
| Тесты | ✅ 18 тестов | все проходят |
| docs/ | ❌ usage.md, format.md | запланированы |

---

## Ключевые изменения по сравнению с первой версией

### L2 — апгрейд до Strict Non-Overlap (DDAS Contract v1)

Первая версия проверяла **только dst∩dst**. Текущая версия заимствует алгоритм из `ddas/src/core/strict_validator.c` (56 строк C) и проверяет:

1. **Self-overlap**: `[src, src+n) ∩ [dst, dst+n)` одной инструкции — недопустимо.
2. **Src∩Src**: source-интервалы двух разных инструкций — недопустимо.
3. **Dst∩Dst**: destination-интервалы — недопустимо.
4. **Src∩Dst / Dst∩Src**: cross-overlap — недопустимо.
5. **Scan-line O(K log K)**: сортировка всех интервалов + линейный проход.

**Спецификация**: `ddas/doc/address_space_contract_v1.md` — «In a single Tick, no bit position may belong to more than one half-open interval participating in copy operations.»

### Snapshot utility

Адаптация `ddas/src/core/snapshot.c` для Python:
- `save_snapshot(tick, space_data, path)` — запись снапшота.
- `load_snapshot(path)` → `(tick, space_data)` — чтение.
- `make_fixture(instrs, slot_size, space_bytes)` — генерация тестового образа.

---

## L1: Memory-Safety Checker

**Цель**: проверить, что все инструкции `copy n, dst, src` в образе пространства:
1. `dst + n <= SPACE_SIZE` — не выходят за границы пространства.
2. `dst` НЕ попадает в защищённые регионы (PROCESSOR, MMIO, ART).
3. `dst` попадает в разрешённый для контракта регион (scratch/workspace).

**Вход**: бинарный образ пространства (raw, тот же формат что у `vmrun --dump-space`).  
**Выход**: PASS / FAIL + список нарушений (номер слота, tick, инструкция).

### Задачи

- `✅ L1.1. Определить формат образа`
  - `✅ L1.1.1. Зафиксировать: образ = дамп `space` (VM_SPACE_BYTES байт)`
  - `✅ L1.1.2. Зафиксировать: конфигурация SPACE_BITS, PROCESSOR_N, поле instr_bits читается из произвольного конфига или определяется автоматически (по умолчанию 512 КБ, 64 слота)`

- `✅ L1.2. Распарсить инструкции из образа`
  - `✅ L1.2.1. Реализовать reader: по адресу слота (i * instr_bits) прочитать n, dst, src`
  - `✅ L1.2.2. Поддержать разные instr_bits (выводятся из SPACE_BITS: addr_bits = round8(log2(SPACE_BITS)), n_bits = addr_bits)`

- `✅ L1.3. Определить защищённые регионы`
  - `✅ L1.3.1. PROCESSOR: [0, PROCESSOR_BITS) — инструкции, нельзя писать сюда (или можно, но с флагом)`
  - `✅ L1.3.2. MMIO: [PROCESSOR_BITS, WORKSPACE_BASE) — канальные handshake-регистры`
  - `✅ L1.3.3. ART: если присутствует — регион ART-таблицы (конфигурируемая область)`
  - `✅ L1.3.4. Scratch (TESTSCR): [TESTSCR_BASE, TESTSCR_END) — разрешённый регион записи для контракта`
  - `✅ L1.3.5. Внешний конфиг: JSON/YAML с описанием protected_regions[] и allowed_regions[]`

- `✅ L1.4. Реализовать проверки`
  - `✅ L1.4.1. boundary_check(dst, n): dst + n <= SPACE_BITS`
  - `✅ L1.4.2. protected_check(dst, n): [dst, dst+n) ∩ protected_regions == ∅`
  - `✅ L1.4.3. allowed_check(dst, n): [dst, dst+n) ⊆ allowed_regions (если регионы заданы)`

- `✅ L1.5. Собрать отчёт`
  - `✅ L1.5.1. Формат отчёта: JSON {status, violations: [{tick, slot, n, dst, src, reason}]}`
  - `✅ L1.5.2. Человекочитаемый вывод с цветами (PASS/FAIL, красный/зелёный)`

- `✅ L1.6. Тесты`
  - `✅ L1.6.1. Тест: корректный образ (ни одного нарушения)`
  - `✅ L1.6.2. Тест: dst+ n > SPACE_BITS (ожидается FAIL)`
  - `✅ L1.6.3. Тест: dst в PROCESSOR (ожидается FAIL)`
  - `✅ L1.6.4. Тест: dst в MMIO (ожидается FAIL)`
  - `✅ L1.6.5. Тест: пустой образ (все NOP) — PASS`
  - `✅ L1.6.6. Тест: с реальным образом add24 (из DPF) — PASS`

---

## L2: Strict Non-Overlap Checker (DDAS Contract v1)

**Цель**: проверить, что внутри каждого tick (слоя) ни один бит пространства не принадлежит более чем одному полуинтервалу `copy(n, dst, src)`.

**Спецификация**: `/home/user/work/ddas/doc/address_space_contract_v1.md`

**Инвариант (п. 3.1-3.3)**:
> In a single Tick, no bit position may belong to more than one half-open interval participating in copy operations.
> This applies to all source and destination intervals.
> Therefore:
>   - Any instruction whose source and destination overlap is invalid.
>   - Any two instructions overlapping in any position are invalid.

**Алгоритм** (заимствован из `ddas/src/core/strict_validator.c`, 56 строк C):
1. Для каждой не-NOP инструкции: проверить self-overlap `[src, src+n) ∩ [dst, dst+n)`.
2. Добавить оба интервала `[src, src+n)` и `[dst, dst+n)` в общий список.
3. Отсортировать все интервалы по `(start, end)`.
4. Scan-line: если `intervals[i].start < intervals[i-1].end` → конфликт.

**Сложность**: O(K log K) на tick, где K = 2 × (число не-NOP инструкций).

**Типы конфликтов**:
| Тип | Описание |
|---|---|
| `self-src-dst` | src и dst одной инструкции пересекаются |
| `src-src` | src двух разных инструкций пересекаются |
| `dst-dst` | dst двух разных инструкций пересекаются |
| `src-dst` | src инструкции A пересекает dst инструкции B |
| `dst-src` | dst инструкции A пересекает src инструкции B |

**Вход**: мульти-слойный образ (последовательность слоёв, каждый — полный набор из PROCESSOR_N инструкций).  
**Выход**: PASS / FAIL + список конфликтов (tick, пара слотов, тип, перекрывающийся диапазон).

### Задачи

- `✅ L2.1. Определить формат мульти-слойного образа`
  - `✅ L2.1.1. Вариант A: один файл = один слой (последовательность файлов)`
  - `✅ L2.1.2. Вариант B: образ = цепочка (каждый слой — отдельное пространство, связанное chain-load)`
  - `✅ L2.1.3. Принять вариант A: каждый `space.dump` — один tick, имена файлов `layer_0000.bin`, `layer_0001.bin``

- `✅ L2.2. Алгоритм полного non-overlap (DDAS strict)`
  - `✅ L2.2.1. Для каждой не-NOP инструкции: generate интервалы [src, src+n) и [dst, dst+n)`
  - `✅ L2.2.2. Проверить self-overlap: src ∩ dst одной инструкции`
  - `✅ L2.2.3. Сортировка всех интервалов по start`
  - `✅ L2.2.4. Scan-line: interval[i].start < interval[i-1].end → conflict`
  - `✅ L2.2.5. Классификация конфликта по типу (src/src/dst/dst/src/cross/self)`

- `✅ L2.3. Оптимизация`
  - `✅ L2.3.1. Scan-line O(K log K) — включён в реализацию`
  - `✅ L2.3.2. Interval tree — опционально для N > 4096`

- `✅ L2.4. Собрать отчёт`
  - `✅ L2.4.1. Формат: JSON {status, conflicts: [{tick, slot_a, slot_b, kind, overlap_begin, overlap_end}]}`
  - `✅ L2.4.2. Человекочитаемый вывод с указанием типа пересечения`

- `✅ L2.5. Тесты`
  - `✅ L2.5.1. Тест: слой без конфликтов (PASS)`
  - `✅ L2.5.2. Тест: два слота пишут в один dst (FAIL)`
  - `✅ L2.5.3. Тест: частичное перекрытие dst (FAIL)`
  - `✅ L2.5.4. Тест: src-конфликт (FAIL — strict mode)`
  - `✅ L2.5.5. Тест: self-overlap src∩dst (FAIL)`
  - `✅ L2.5.6. Тест: cross-overlap src∩dst разных слотов (FAIL)`
  - `✅ L2.5.7. Тест: реальный образ add24 из DPF (TBD при генерации фикстур)`

---

## Snapshot Utility

**Адаптация**: `ddas/src/core/snapshot.c` → `src/snapshot.py`

- `✅ SNAP.1. save_snapshot(tick, space_data, path)` — бинарный снапшот.
- `✅ SNAP.2. load_snapshot(path) → (tick, space_data)` — чтение.
- `✅ SNAP.3. make_fixture(instrs, slot_size, space_bytes)` — генерация тестового образа из списка инструкций.
- `❌ SNAP.4. Интеграция в тесты с реальными образами DPF (add24.bin, life.bin)`

---

## Интеграция (L1 + L2)

- `✅ INT.1. Объединить L1 и L2 в один инструмент: `spaces-verify``
  - `✅ INT.1.1. CLI: `spaces-verify --layers layer_*.bin --config verify.json``
  - `✅ INT.1.2. Сначала L1 на каждом слое, потом L2 на всей последовательности`

- `✅ INT.2. CI-ready`
  - `✅ INT.2.1. Exit code: 0 = PASS, 1 = FAIL, 2 = ошибка парсинга`
  - `✅ INT.2.2. JSON-отчёт пригоден для CI артефактов`

- `❌ INT.3. Документация`
  - `❌ INT.3.1. docs/usage.md — как запускать`
  - `❌ INT.3.2. docs/format.md — формат конфига и образа`
  - `❌ INT.3.3. README.md — overview`

---

## Выбор языка

| Критерий | Python | C | Rust |
|---|---|---|---|
| Скорость разработки | ✅ (дни) | 🟡 (недели) | 🟡 (недели) |
| Производительность | 🟡 (достаточно) | ✅ | ✅ |
| Пригодность для CI | 🟡 (требует py env) | ✅ | ✅ |
| Чтение бинарных образов | struct.unpack / numpy | ✅ memcpy | ✅ |
| Работа с SMT (будущее) | ✅ Z3.py | ❌ | 🟡 (z3-sys) |

**Решение**: Python + `argparse` + `struct` (никаких зависимостей, кроме stdlib).  
Если в будущем понадобится SMT — Z3.py подключается безболезненно.

---

## Оценка времени (обновлённая)

| Компонент | Время | Статус |
|---|---|---|
| L1 (memory-safety) | 4 дня | ✅ |
| L2 (strict non-overlap) | 3 дня (включая апгрейд) | ✅ |
| Snapshot | 1 день | ✅ |
| Интеграция | 2 дня | ✅ (кроме docs) |
| **Total** | **~10 дней** | **~90%** |

---

## Файловая структура

```
smartcontract-verifier/
├── README.md                    # ❌ (todo)
├── roadmap.md                   # ✅ этот файл
├── docs/                        # ❌ (todo)
│   ├── usage.md
│   └── format.md
├── src/
│   ├── __init__.py              # ✅
│   ├── spaces_verify.py         # ✅ MAIN: парсинг аргументов, диспетчеризация
│   ├── image_reader.py          # ✅ L1.2: чтение инструкций из образа
│   ├── config.py                # ✅ L1.3: конфиг регионов
│   ├── memory_check.py          # ✅ L1.4: memory-safety проверки
│   ├── conflict_check.py        # ✅ L2.2: strict non-overlap (DDAS v1)
│   ├── snapshot.py              # ✅ save/load/fixture generation
│   └── report.py                # ✅ L1.5+L2.4: отчёт
├── tests/
│   ├── __init__.py
│   ├── test_image_reader.py     # ✅
│   ├── test_memory_check.py     # ✅
│   ├── test_conflict_check.py   # ✅ (обновлён: strict mode)
│   ├── test_snapshot.py         # ❌ (todo)
│   └── fixtures/
│       ├── empty.bin            # ✅
│       ├── oob_dst.bin          # ✅
│       ├── conflict_same_dst.bin# ✅
│       ├── add24_layer_0.bin    # ❌ (todo)
│       └── add8_layer_0.bin     # ❌ (todo)
└── config/
    └── default_config.json      # ✅
```
