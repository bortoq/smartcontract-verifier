# space-verifier

**Formal verifier for a single-instruction smart contract VM.**

This project implements a two-layer formal verifier (L1 + L2) for smart contracts
targeting a research VM whose **only** instruction is `copy(n, dst, src)` —
a bit-range copy on a flat, bit-addressable memory.

---

## Why this matters

Formal verification of smart contracts is notoriously hard. In EVM, verifying that
a contract doesn't write out of bounds or create a race condition requires SMT solvers
(Z3), custom invariants, and expert effort.

This project explores an alternative: **a VM designed for verifiability from the ground up**.

| Approach | Complexity | Dependencies |
|---|---|---|
| EVM + SMT solver | O(n²) or more per check | Z3, custom specs |
| **This VM (L1 memory safety)** | **O(n) per contract** | **stdlib only** |
| **This VM (L2 conflict freedom)** | **O(K log K) per round** | **stdlib only** |

The key insight: a single instruction `copy(n, dst, src)` on flat memory makes
formal verification **trivial** — no SMT, no model checking, no expert effort.

---

## Architecture

### VM Model

```
┌─────────────────────────────────────────────────────┐
│                   Memory (bit-addressable)           │
│  ┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐  │
│  │  0  │  1  │  2  │ ... │  N  │ ... │ ... │  M  │  │
│  └─▲───┴──▲──┴──▲──┴──▲──┴──▲──┴─────┴─────┴─────┘  │
│    │      │     │     │     │                         │
│  copy  copy  copy  copy  copy  ...                   │
│  (n,dst,src)  (n,dst,src)  ...  <── per round        │
└─────────────────────────────────────────────────────┘
```

- **Memory**: flat bit-addressable array of `S` bits.
- **Instruction**: `copy(n, dst, src)` — copies `n` bits from `[src, src+n)` to `[dst, dst+n)`.
- **Execution round (tick)**: up to `P` contracts execute simultaneously, each in their own slot.
- **NOP** (`n=0`): no-op instruction, the contract is idle.

### L1 — Memory Safety Checker

For each instruction, verifies:

1. **Boundary**: `dst + n <= S` — no out-of-bounds write.
2. **Protected regions**: `dst` is not in the code section, I/O area, or configuration table.
3. **Allowed regions**: `dst` is within the contract's designated workspace (if restrictions are configured).

**Complexity**: O(number of contracts) per round.  
**Implementation**: `src/memory_check.py` (80 lines).

### L2 — Strict Conflict-Free Checker

Verifies that within a single round, **no bit position belongs to more than one operation**.

For each non-NOP instruction, two intervals are generated: `[src, src+n)` and `[dst, dst+n)`.
All intervals are sorted, then scanned linearly. If `interval[i].start < interval[i-1].end`,
a conflict is reported.

Detected conflict types:

| Type | Meaning |
|---|---|
| `dst ∩ dst` | Two contracts write to the same location |
| `src ∩ src` | Two contracts read from the same source |
| `src ∩ dst` | One contract reads where another writes |
| `self src ∩ dst` | A contract reads and writes overlapping ranges |

**Complexity**: O(K log K) per round, where K = 2 × active contracts.  
**Implementation**: `src/conflict_check.py` (130 lines).

---

## How it compares

| Criterion | EVM (Solidity) | Solana SVM | RISC-V zkVM | This VM |
|---|---|---|---|---|
| Instruction set | ~140 opcodes | ~100 instructions | full ISA | **1 instruction** |
| Memory model | word-addressed, segmented | page-based | byte-addressed | **flat bit-addressable** |
| Memory safety verification | requires Z3/SMT | requires Z3/SMT | requires SMT | **O(n) — stdlib** |
| Race condition check | requires Z3/SMT | built-in runtime | N/A | **O(K log K) — stdlib** |
| TCB (trusted computing base) | thousands of LOC | thousands of LOC | hundreds of LOC | **~390 lines C** |
| Suitability for production | ✅ | ✅ | ✅ | ❌ research |

This VM is **not** a production replacement for EVM or Solana. It is a **research prototype**
exploring the question: *what if formal verification was the default, not an afterthought?*

---

## Quick start

```bash
# Install
pip install -e .

# Run all tests
make test

# Verify a single execution round (L1 + L2)
spaces-verify --image tests/fixtures/sample.bin --config config/default_config.json

# Verify a multi-round execution trace
spaces-verify --layers tests/fixtures/round_*.bin --config config/default_config.json

# JSON output (CI-friendly)
spaces-verify --layers tests/fixtures/round_*.bin --config config/default_config.json --format json

# L2 only (skip memory safety)
spaces-verify --layers tests/fixtures/round_*.bin --config config/default_config.json --l2-only
```

Exit codes: `0` = PASS, `1` = FAIL, `2` = error.

---

## Project structure

```
src/
  spaces_verify.py     # CLI entry point
  image_reader.py      # parse binary memory image into instructions
  config.py            # memory layout configuration (protected/allowed regions)
  memory_check.py      # L1: memory safety (boundary, protected, allowed regions)
  conflict_check.py    # L2: strict conflict freedom (scan-line, O(K log K))
  snapshot.py          # save/load memory state, generate test fixtures
  report.py            # JSON + human-readable report formatting
tests/
  test_conflict_check.py   # 13 tests for L2
  test_image_reader.py     # 4 tests for binary parsing
  test_memory_check.py     # 8 tests for L1
  fixtures/                # binary test images
config/
  default_config.json      # default memory layout configuration
```

---

## Formal specification (L2 invariant)

> In a single execution round, no bit position may belong to more than one
> half-open interval participating in `copy` operations.
> This applies to all source and destination intervals.
>
> Therefore:
>   - Any instruction whose source and destination overlap is invalid.
>   - Any two instructions overlapping in any position are invalid.

This invariant guarantees deterministic, race-free parallel execution.

---

## Roadmap

See [roadmap.md](roadmap.md) for current status and planned work.

## License

MIT

---

## VM Runtime (C implementation)

The `src/vm/` directory contains the reference implementation of the VM
that actually executes `copy(n, dst, src)` instructions:

```
src/vm/
  space.h / space.c    # VM core: init, MMIO handshake, tick execution
  bitcpy.c             # bit-range copy with overlap-safe fallback
  invariants.h/.c      # optional runtime checks (32-bit alignment)
  Makefile             # builds libvm.a
  test_vm.c            # minimal smoke test
```

Build with:

```bash
cd src/vm && make && make test
```

### Integration with the verifier

See [docs/vm-integration.md](docs/vm-integration.md) for four integration strategies:

1. **Property-based testing** — generate random images, verify + execute, compare.
2. **Reference trace** — capture execution trace via hooks, verify offline.
3. **Runtime verification** — embed L1/L2 checks into C for in-VM safety.
4. **CI pipeline** — verify-then-run: reject invalid images before execution.

The C runtime is ~700 lines (TCB). The verifier (Python) is ~400 lines.
Together they form a complete formally-verifiable smart contract platform.
