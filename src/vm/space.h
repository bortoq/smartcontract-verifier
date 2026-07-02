/* space.h — Copy-Space VM core
 *
 * Model:
 * - Single memory vm->space[] (SPACE_BYTES), addressed in bits.
 * - Only computation primitive: copy(n_bits, dst_bit, src_bit).
 * - "Processor" is a memory region with PROCESSOR_N instruction slots.
 * - One VM tick:
 *     (1) services MMIO (stdin/stdout/halt) via handshake registers,
 *     (2) executes slots 0..PROCESSOR_N-1 (fetch-execute).
 *
 * Instruction encoding:
 * - three fields: n, dst, src
 * - address width (ADDR_BITS) derived from SPACE_BYTES
 * - N_BITS = ADDR_BITS
 * - INSTR_BITS = 3 * ADDR_BITS (ADDR_BITS is rounded up to a multiple of 8)
 * - bit numbering inside a byte: bit0 is MSB (0x80), MSB-first.
 *
 * Layered execution (loader 3B):
 * - VM has no built-in layer switching state.
 * - Next layer loading is implemented by copycode:
 *     slot0 is NOP (n=0) but its dst field carries the next layer bit address
 *     slot PROCESSOR_N-2 patches the src field of slot PROCESSOR_N-1
 *     slot PROCESSOR_N-1 copies PROCESSOR_BITS from the next layer into the processor area
 */

#ifndef COPYSPACE_H_
#define COPYSPACE_H_

#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <limits.h>

#if CHAR_BIT != 8
#  error "Copy-Space VM requires CHAR_BIT==8"
#endif

/* -------------------- User-tunable knobs -------------------- */

/* Default: 512 KiB */
#ifndef VM_SPACE_BYTES
#define VM_SPACE_BYTES (512u * 1024u)
#endif

/* Default: 64 slots */
#ifndef VM_PROCESSOR_N
#define VM_PROCESSOR_N 64u
#endif

/* -------------------- Types -------------------- */

typedef uint64_t bitaddr_t;

typedef struct {
  uint64_t n;
  uint64_t dst;
  uint64_t src;
} vm_inst_t;


/* -------------------- VM error diagnostics (recorded on VM_ERR) -------------------- */

typedef enum {
  VM_E_NONE = 0,
  VM_E_SRC_BOUNDS = 1,
  VM_E_DST_BOUNDS = 2,
  VM_E_ALIGN32 = 3
} vm_err_kind_t;

typedef struct {
  vm_err_kind_t kind;
  uint64_t tick;     /* 0-based tick index */
  unsigned slot;     /* processor slot index */
  vm_inst_t ins;     /* offending instruction */
  bitaddr_t space_bits;
} vm_err_t;

/* Optional host-side hooks (instrumentation). VM core calls them if non-NULL. */
typedef struct vm_hooks {
  void *user;
  void (*tick_begin)(void *user, size_t slots_cap);
  void (*note_copy)(void *user, uint64_t dst, uint64_t n, uint64_t src);
  void (*tick_end)(void *user);
} vm_hooks_t;

/* VM return codes */
typedef enum {
  VM_OK   = 0,   /* tick completed */
  VM_HALT = 1,   /* halted by MMIO.HALT */
  VM_ERR  = -1   /* error (I/O, bounds, invariants, etc) */
} vm_rc_t;

/* -------------------- VM object -------------------- */

typedef struct vm_mmio_layout {
  bitaddr_t base;

  /* IN channel */
  bitaddr_t in_req;   /* 1 bit */
  bitaddr_t in_done;  /* 1 bit */
  bitaddr_t in_eof;   /* 1 bit */
  bitaddr_t in_err;   /* 1 bit */
  bitaddr_t in_dst;   /* ADDR_BITS */
  bitaddr_t in_len;   /* N_BITS */
  bitaddr_t in_got;   /* N_BITS */

  /* OUT channel */
  bitaddr_t out_req;  /* 1 bit */
  bitaddr_t out_done; /* 1 bit */
  bitaddr_t out_err;  /* 1 bit */
  bitaddr_t out_src;  /* ADDR_BITS */
  bitaddr_t out_len;  /* N_BITS */
  bitaddr_t out_got;  /* N_BITS */

  /* Control */
  bitaddr_t halt;     /* 1 bit */

  bitaddr_t end;      /* 1 past end */
} vm_mmio_layout_t;

typedef struct vm {
  uint8_t  *space;
  size_t    space_bytes;
  bitaddr_t space_bits;

  unsigned  processor_n;

  /* derived widths */
  unsigned  addr_bits;     /* rounded up to multiple of 8 */
  unsigned  n_bits;        /* == addr_bits */
  unsigned  instr_bits;    /* == 3*addr_bits */
  unsigned  instr_bytes;   /* instr_bits/8 */

  bitaddr_t processor_start; /* 0 */
  bitaddr_t processor_bits;  /* processor_n * instr_bits */

  /* field offsets inside instruction */
  unsigned off_n;     /* 0 */
  unsigned off_dst;   /* n_bits */
  unsigned off_src;   /* n_bits + addr_bits */

  vm_mmio_layout_t mmio;

  /* conventional workspace base (first free bit after MMIO) */
  bitaddr_t workspace_base;
  vm_hooks_t hooks;

  /* diagnostics */
  int strict_align32; /* if set, enforce 32-bit alignment for VAR_AP/VAR_BP/VAR_RP (std7_fixed) */
  uint64_t tick_counter; /* increments per vm_tick() call that completes */
  vm_err_t last_err;

} vm_t;

/* -------------------- Bit copy primitive -------------------- */

void bitcpy(size_t n_bits,
            const void *src_org, size_t src_bit,
            void *dst_org, size_t dst_bit);

/* -------------------- VM API -------------------- */

int     vm_init(vm_t *vm, size_t space_bytes, unsigned processor_n);
void    vm_free(vm_t *vm);

vm_rc_t vm_tick(vm_t *vm, FILE *in, FILE *out);
vm_rc_t vm_run(vm_t *vm, uint64_t life, FILE *in, FILE *out);

/* -------------------- Encoding helpers (arbitrary bit width) -------------------- */

/* bit get/set (MSB-first within byte) */
unsigned vm_bit_get(const vm_t *vm, bitaddr_t pos);
void     vm_bit_set(vm_t *vm, bitaddr_t pos, unsigned v);

/* read/write up to 64-bit unsigned, MSB-first */
uint64_t vm_read_uint(const vm_t *vm, bitaddr_t pos, unsigned width);
void     vm_write_uint(vm_t *vm, bitaddr_t pos, unsigned width, uint64_t value);

/* instruction read/write at bit address ip */
vm_inst_t vm_read_inst(const vm_t *vm, bitaddr_t ip);
void      vm_write_inst(vm_t *vm, bitaddr_t ip, vm_inst_t in);

/* processor slot addressing */
static inline bitaddr_t vm_proc_slot_ip(const vm_t *vm, unsigned slot) {
  return vm->processor_start + (bitaddr_t)slot * (bitaddr_t)vm->instr_bits;
}
static inline bitaddr_t vm_proc_slot_field_ip(const vm_t *vm, unsigned slot, unsigned field_off_bits) {
  return vm_proc_slot_ip(vm, slot) + (bitaddr_t)field_off_bits;
}

/* -------------------- Convenience: build a minimal boot layer with loader 3B --------------------
 *
 * This function is not VM semantics. It is a convenience helper that writes copycode
 * into the processor area.
 *
 * Loader 3B convention:
 * - slot0: NOP (n=0), but its dst field carries next_layer_ptr (bit address)
 * - patch_slot = PROCESSOR_N-2:
 *     copy ADDR_BITS, dst = (src-field of load_slot), src = (dst-field of slot0)
 * - load_slot = PROCESSOR_N-1:
 *     copy PROCESSOR_BITS, dst = PROCESSOR_START, src = (patched)
 *
 * After one tick, the boot layer loads the layer at next_layer_ptr into the processor.
 */
int vm_build_boot_loader_layer(vm_t *vm, bitaddr_t next_layer_ptr);

#endif /* COPYSPACE_H_ */
