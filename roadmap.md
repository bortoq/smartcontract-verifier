# Roadmap

**Project**: `space-verifier` — formal verifier (L1 + L2) for a single-instruction smart contract VM.  
**Repository**: `/home/user/work/smartcontract-verifier/`

---

## Status

| Component | Status | Notes |
|---|---|---|
| L1: Memory-Safety Checker | ✅ Done | boundary + protected + allowed regions |
| L2: Conflict-Free Checker | ✅ Done | strict non-overlap, 5 conflict types |
| Snapshot utility | ✅ Done | save/load state, fixture generation |
| CLI `spaces-verify` | ✅ Done | L1+L2, JSON/text, CI exit codes |
| Tests | ✅ Done | 25 tests, all passing |
| docs/ | ❌ Todo | usage.md, format.md |

---

## L1: Memory-Safety Checker

**Goal**: verify that every `copy(n, dst, src)` instruction in a memory image satisfies:

1. `dst + n <= S` — no out-of-bounds write.
2. `dst` does not fall into a protected region (code section, I/O area, config table).
3. `dst` falls into a region allowed for the contract (workspace).

**Input**: binary memory image (raw dump of the VM state).  
**Output**: PASS / FAIL + list of violations (slot, round, instruction).

### Tasks

- `✅ L1.1. Define image format`
  - `✅ L1.1.1. Fixed: image = memory dump (VM_MEMORY_SIZE bytes)`
  - `✅ L1.1.2. Fixed: configuration MEMORY_BITS, CONTRACT_COUNT, instruction bit-width read from config or auto-detected (default 512 KiB, 64 slots)`

- `✅ L1.2. Parse instructions from image`
  - `✅ L1.2.1. Implement reader: at slot address (i * instr_bits) read n, dst, src`
  - `✅ L1.2.2. Support variable instr_bits (derived from MEMORY_BITS: addr_bits = round8(log2(MEMORY_BITS)), n_bits = addr_bits)`

- `✅ L1.3. Define protected regions`
  - `✅ L1.3.1. CODE: [0, CODE_BITS) — instruction area, writes forbidden`
  - `✅ L1.3.2. IO: [CODE_BITS, WORKSPACE_BASE) — channel handshake registers`
  - `✅ L1.3.3. CONFIG_TABLE: if present — configuration table region (configurable)`
  - `✅ L1.3.4. HEAP (WORKSPACE): [HEAP_BASE, HEAP_END) — allowed write region for contracts`
  - `✅ L1.3.5. External JSON config: protected_regions[] and allowed_regions[]`

- `✅ L1.4. Implement checks`
  - `✅ L1.4.1. boundary_check(dst, n): dst + n <= MEMORY_BITS`
  - `✅ L1.4.2. protected_check(dst, n): [dst, dst+n) ∩ protected_regions == ∅`
  - `✅ L1.4.3. allowed_check(dst, n): [dst, dst+n) ⊆ allowed_regions (if configured)`

- `✅ L1.5. Report`
  - `✅ L1.5.1. JSON format: {status, violations: [{round, slot, n, dst, src, reason}]}`
  - `✅ L1.5.2. Human-readable output with colors`

- `✅ L1.6. Tests`
  - `✅ L1.6.1. Valid image (no violations)`
  - `✅ L1.6.2. dst + n > MEMORY_BITS (expect FAIL)`
  - `✅ L1.6.3. dst in CODE region (expect FAIL)`
  - `✅ L1.6.4. dst in IO region (expect FAIL)`
  - `✅ L1.6.5. Empty image (all NOP) — PASS`
  - `✅ L1.6.6. Real contract bytecode — PASS (TBD: generate fixtures)`

---

## L2: Strict Non-Overlap Checker

**Goal**: verify that within each execution round, no bit belongs to more than one
`copy(n, dst, src)` interval.

**Invariant**:
> In a single round, no bit position may belong to more than one
> half-open interval participating in `copy` operations.
> This applies to all source and destination intervals.
> Therefore:
>   - Any instruction whose source and destination overlap is invalid.
>   - Any two instructions overlapping in any position is invalid.

**Algorithm**:
1. For each non-NOP instruction: check self-overlap `[src, src+n) ∩ [dst, dst+n)`.
2. Collect both intervals `[src, src+n)` and `[dst, dst+n)` into a list.
3. Sort all intervals by `(start, end)`.
4. Scan: if `intervals[i].start < intervals[i-1].end` → conflict.

**Complexity**: O(K log K) per round, where K = 2 × active contracts.

**Conflict types**:

| Type | Description |
|---|---|
| `self-src-dst` | src and dst of the same instruction overlap |
| `src-src` | src intervals of two different instructions overlap |
| `dst-dst` | dst intervals of two different instructions overlap |
| `src-dst` | src of instruction A overlaps dst of instruction B |
| `dst-src` | dst of instruction A overlaps src of instruction B |

**Input**: multi-round trace (sequence of memory images, one per execution round).  
**Output**: PASS / FAIL + list of conflicts (round, slot pair, type, overlapping range).

### Tasks

- `✅ L2.1. Define multi-round format`
  - `✅ L2.1.1. Option A: one file = one round (sequence of files)`
  - `✅ L2.1.2. Option B: one file = chain of rounds (linked by chain-load)`
  - `✅ L2.1.3. Adopted: Option A, file naming: round_0000.bin, round_0001.bin, ...`

- `✅ L2.2. Strict non-overlap algorithm`
  - `✅ L2.2.1. For each non-NOP: generate intervals [src, src+n) and [dst, dst+n)`
  - `✅ L2.2.2. Check self-overlap: src ∩ dst of the same instruction`
  - `✅ L2.2.3. Sort all intervals by start`
  - `✅ L2.2.4. Scan: interval[i].start < interval[i-1].end → conflict`
  - `✅ L2.2.5. Classify conflict type (src/src, dst/dst, cross, self)`

- `✅ L2.3. Optimization`
  - `✅ L2.3.1. Scan-line O(K log K) — implemented`
  - `✅ L2.3.2. Interval tree — optional for N > 4096`

- `✅ L2.4. Report`
  - `✅ L2.4.1. JSON format: {status, conflicts: [{round, slot_a, slot_b, kind, overlap_begin, overlap_end}]}`
  - `✅ L2.4.2. Human-readable output with conflict type labels`

- `✅ L2.5. Tests`
  - `✅ L2.5.1. Round with no conflicts (PASS)`
  - `✅ L2.5.2. Two slots write to same dst (FAIL)`
  - `✅ L2.5.3. Partial dst overlap (FAIL)`
  - `✅ L2.5.4. Source conflict src∩src (FAIL — strict mode)`
  - `✅ L2.5.5. Self-overlap src∩dst of same contract (FAIL)`
  - `✅ L2.5.6. Cross-overlap src of A ∩ dst of B (FAIL)`
  - `✅ L2.5.7. Real contract bytecode (TBD: generate fixtures)`

---

## Snapshot Utility

- `✅ SNAP.1. save_snapshot(round, memory_data, path)` — binary snapshot write.
- `✅ SNAP.2. load_snapshot(path) → (round, memory_data)` — binary snapshot read.
- `✅ SNAP.3. make_fixture(instructions, slot_size, memory_size)` — generate test image from instruction list.
- `❌ SNAP.4. Integrate with real contract bytecode fixtures`

---

## Integration (L1 + L2)

- `✅ INT.1. Unified CLI: spaces-verify`
  - `✅ INT.1.1. spaces-verify --layers round_*.bin --config verify.json`
  - `✅ INT.1.2. Runs L1 on each round, then L2 on the full sequence`

- `✅ INT.2. CI-ready`
  - `✅ INT.2.1. Exit code: 0 = PASS, 1 = FAIL, 2 = parse error`
  - `✅ INT.2.2. JSON report suitable for CI artifacts`

- `❌ INT.3. Documentation`
  - `❌ INT.3.1. docs/usage.md`
  - `❌ INT.3.2. docs/format.md`
  - `❌ INT.3.3. README.md — overview`

---

## Design decisions

### Language choice: Python

| Criterion | Python | C | Rust |
|---|---|---|---|
| Development speed | ✅ (days) | 🟡 (weeks) | 🟡 (weeks) |
| Performance | 🟡 (sufficient) | ✅ | ✅ |
| CI readiness | 🟡 (needs Python) | ✅ | ✅ |
| Binary image parsing | struct / numpy | ✅ memcpy | ✅ |
| Future SMT integration | ✅ Z3.py | ❌ | 🟡 (z3-sys) |

**Decision**: Python + `argparse` + `struct` (stdlib only, zero external dependencies).  
If SMT is ever needed, Z3.py can be added without friction.

### Why a single instruction VM?

The entire project hinges on one observation: **a single-instruction VM with flat memory
makes formal verification trivial**. The TCB (trusted computing base) is ~390 lines of C.
For comparison, verifying memory safety in EVM requires an SMT solver and expert-written
invariants. Here, it's a single loop over the instructions.

This is not a production VM — it's a research prototype that asks:
*what if we designed a VM for verifiability first?*

---

## Estimated effort

| Component | Time | Status |
|---|---|---|
| L1 (memory safety) | 4 days | ✅ |
| L2 (strict non-overlap) | 3 days | ✅ |
| Snapshot | 1 day | ✅ |
| Integration | 2 days | ✅ (except docs) |
| **Total** | **~10 days** | **~90%** |

---

## File structure

```
smartcontract-verifier/
├── README.md                    # ✅ (rewritten)
├── roadmap.md                   # ✅ this file
├── docs/                        # ❌ (todo)
│   ├── usage.md
│   └── format.md
├── src/
│   ├── __init__.py              # ✅
│   ├── spaces_verify.py         # ✅ CLI entry point
│   ├── image_reader.py          # ✅ binary image parser
│   ├── config.py                # ✅ memory layout configuration
│   ├── memory_check.py          # ✅ L1: memory safety
│   ├── conflict_check.py        # ✅ L2: strict non-overlap
│   ├── snapshot.py              # ✅ save/load/fixture generation
│   └── report.py                # ✅ report formatting
├── tests/
│   ├── __init__.py
│   ├── test_conflict_check.py   # ✅ 13 tests
│   ├── test_image_reader.py     # ✅ 4 tests
│   ├── test_memory_check.py     # ✅ 8 tests
│   ├── test_snapshot.py         # ❌ (todo)
│   └── fixtures/
│       ├── sample.bin           # ❌ (sample fixture)
│       ├── oob_dst.bin          # ✅
│       └── conflict_same_dst.bin# ✅
└── config/
    └── default_config.json      # ✅
```
