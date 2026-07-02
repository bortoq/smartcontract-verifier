# VM Runtime Integration — как использовать рантайм с верификатором

## Структура

```
src/vm/
  space.h          # VM API (типы, vm_init, vm_tick, vm_run)
  space.c          # ядро VM (init, MMIO, tick execution)
  bitcpy.c         # copy(n, dst, src) — единственная инструкция
  invariants.h     # опциональные runtime-инварианты
  invariants.c     # 32-bit alignment проверки для std7_fixed
  Makefile         # сборка статической библиотеки libvm.a
  test_vm.c        # минимальный тест (make test)
```

## Варианты использования

### 1. Property-Based Testing: верификатор vs реальное исполнение

Идея: сгенерировать случайную корректную конфигурацию инструкций,
прогнать через оба инструмента и убедиться что результаты совпадают:

```
Генератор случайных инструкций
       │
       ├──→ spaces-verify (Python) → PASS/FAIL + отчёт
       │
       └──→ vm_tick (C runtime)    → OK/ERR + итоговое состояние
```

**Что проверяется:**
- Если `spaces-verify` сказал PASS → vm_tick не должен упасть с VM_ERR.
- Если `spaces-verify` сказал FAIL → vm_tick может упасть (race condition в L2).
- После успешного tick состояние памяти соответствует `copy`-семантике.

**Как реализовать:** написать Python-скрипт, который:
1. Генерирует набор инструкций.
2. Записывает их в сырой дамп памяти.
3. Запускает `spaces-verify` через subprocess.
4. Запускает `vm_tick` через C FFI (ctypes/cffi) или через shell.
5. Сравнивает результаты.

---

### 2. Reference Trace: трассировка исполнения

Идея: прогнать контракт через VM с включёнными hooks
(`tick_begin`, `note_copy`, `tick_end`) и получить точный trace.
Затем проверить этот trace верификатором.

```
Контракт (бинарный образ)
       │
       ├──→ vm_run с hooks → trace.log (все copy-операции)
       │
       └──→ spaces-verify --layers trace.bin → отчёт
```

**Что даёт:**
- Независимая валидация: trace, записанный рантаймом, должен проходить
  верификацию (иначе баг в рантайме или верификаторе).
- Возможность детектить race conditions, которые рантайм не проверяет
  (DPF space.c проверяет только bounds, а L2 — ещё и overlap).

**Как реализовать:** доработать `note_copy` hook так, чтобы он сериализовал
каждую операцию в protobuf/JSON/бинарный формат, читаемый Python.

---

### 3. Runtime Verification (in-VM checking)

Идея: встроить L1/L2 проверки **внутрь** C-рантайма, чтобы VM
отказывалась исполнять опасные операции на месте.

```
vm_tick() {
    // 1. MMIO
    // 2. L1: bound check (уже есть в space.c)
    // 3. L2: strict non-overlap (CHECK ВСТАВЛЯЕТСЯ СЮДА)
    // 4. bitcpy
}
```

**Что даёт:**
- Безопасность по умолчанию: VM не может исполнить конфликтующий набор.
- Единая кодовая база для верификации и исполнения.

**Как реализовать:**
- Портировать `ConflictChecker._check_tick()` на C (56 строк в DDAS strict_validator.c — уже готовый прототип).
- Вставить вызов в `vm_tick()` перед циклом `bitcpy`.

---

### 4. CI пайплайн: verify-then-run

```
# 1. Верификация (быстро, Python)
spaces-verify --image contract.bin --config prod.json
if [ $? -ne 0 ]; then exit 1; fi

# 2. Исполнение (медленно, C)
./vm_run --image contract.bin --life 1000
```

**Что даёт:**
- Контракт не попадёт в исполнение, если не прошёл верификацию.
- Верификация занимает миллисекунды, исполнение — секунды.

---

## Быстрый старт

```bash
# Собрать рантайм
cd src/vm && make

# Запустить тест
make test

# Использовать как библиотеку
# В вашем C-коде:
#   #include "space.h"
#   gcc -I. -L. -o my_program my_program.c -lvm
```

## Ограничения

- Рантайм требует C11+ компилятор.
- `vm_tick()` не thread-safe (один поток на один `vm_t`).
- MMIO (`service_in`/`service_out`) использует `FILE*` — не подходит для
  embedded без адаптации.
- Инварианты (`invariants.c`) завязаны на std7_fixed ABI (ART layout,
  32-bit alignment) — опциональны, не влияют на базовую семантику.
