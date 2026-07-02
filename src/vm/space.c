/* space.c — VM core implementation and MMIO handshake
 */

#include "space.h"
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>

/* -------- utilities: ceil_log2 and rounding -------- */

static unsigned ceil_log2_u64(uint64_t x) {
  /* minimal k such that 2^k >= x; x>=1 */
  unsigned k = 0;
  uint64_t p = 1;
  while (p < x) { p <<= 1; k++; }
  return k;
}
static unsigned round_up_to_8(unsigned x) {
  return (x + 7u) & ~7u;
}

/* -------- bit primitives (MSB-first) -------- */

unsigned vm_bit_get(const vm_t *vm, bitaddr_t pos) {
  uint8_t byte = vm->space[(size_t)(pos >> 3)];
  unsigned shift = 7u - (unsigned)(pos & 7u);
  return (byte >> shift) & 1u;
}

void vm_bit_set(vm_t *vm, bitaddr_t pos, unsigned v) {
  uint8_t *b = &vm->space[(size_t)(pos >> 3)];
  unsigned shift = 7u - (unsigned)(pos & 7u);
  uint8_t mask = (uint8_t)(1u << shift);
  if (v) *b |= mask;
  else   *b &= (uint8_t)~mask;
}

uint64_t vm_read_uint(const vm_t *vm, bitaddr_t pos, unsigned width) {
  if (width == 0 || width > 64) return 0;
  uint64_t v = 0;
  for (unsigned i = 0; i < width; i++) {
    v = (v << 1) | (uint64_t)vm_bit_get(vm, pos + (bitaddr_t)i);
  }
  return v;
}

void vm_write_uint(vm_t *vm, bitaddr_t pos, unsigned width, uint64_t value) {
  if (width == 0 || width > 64) return;
  for (unsigned i = 0; i < width; i++) {
    unsigned bit = (unsigned)((value >> (width - 1u - i)) & 1u);
    vm_bit_set(vm, pos + (bitaddr_t)i, bit);
  }
}

/* -------- instruction encoding -------- */

vm_inst_t vm_read_inst(const vm_t *vm, bitaddr_t ip) {
  vm_inst_t in;
  in.n   = vm_read_uint(vm, ip + (bitaddr_t)vm->off_n,   vm->n_bits);
  in.dst = vm_read_uint(vm, ip + (bitaddr_t)vm->off_dst, vm->addr_bits);
  in.src = vm_read_uint(vm, ip + (bitaddr_t)vm->off_src, vm->addr_bits);
  return in;
}

void vm_write_inst(vm_t *vm, bitaddr_t ip, vm_inst_t in) {
  vm_write_uint(vm, ip + (bitaddr_t)vm->off_n,   vm->n_bits,   in.n);
  vm_write_uint(vm, ip + (bitaddr_t)vm->off_dst, vm->addr_bits, in.dst);
  vm_write_uint(vm, ip + (bitaddr_t)vm->off_src, vm->addr_bits, in.src);
}

/* -------- MMIO layout -------- */

static void vm_compute_mmio_layout(vm_t *vm) {
  /* Place MMIO right after processor area. */
  bitaddr_t p = vm->processor_bits;
  vm->mmio.base = p;

  /* IN */
  vm->mmio.in_req  = p; p += 1;
  vm->mmio.in_done = p; p += 1;
  vm->mmio.in_eof  = p; p += 1;
  vm->mmio.in_err  = p; p += 1;

  vm->mmio.in_dst  = p; p += vm->addr_bits;
  vm->mmio.in_len  = p; p += vm->n_bits;
  vm->mmio.in_got  = p; p += vm->n_bits;

  /* OUT */
  vm->mmio.out_req  = p; p += 1;
  vm->mmio.out_done = p; p += 1;
  vm->mmio.out_err  = p; p += 1;

  vm->mmio.out_src  = p; p += vm->addr_bits;
  vm->mmio.out_len  = p; p += vm->n_bits;
  vm->mmio.out_got  = p; p += vm->n_bits;

  /* Control */
  vm->mmio.halt = p; p += 1;

  /* round MMIO end up to next byte boundary for nicer workspace */
  vm->mmio.end = (p + 7u) & ~(bitaddr_t)7u;
  vm->workspace_base = vm->mmio.end;
}

/* -------- init/free -------- */

int vm_init(vm_t *vm, size_t space_bytes, unsigned processor_n) {
  if (!vm) return -1;
  memset(vm, 0, sizeof *vm);

  if (space_bytes == 0) return -1;
  if (processor_n == 0) return -1;

  vm->space = (uint8_t*)calloc(1, space_bytes);
  if (!vm->space) return -1;

  vm->space_bytes = space_bytes;
  vm->space_bits  = (bitaddr_t)space_bytes * 8u;
  vm->processor_n = processor_n;

  /* derive widths */
  unsigned raw = ceil_log2_u64((uint64_t)vm->space_bits);
  vm->addr_bits = round_up_to_8(raw);
  if (vm->addr_bits < 8) vm->addr_bits = 8;

  vm->n_bits = vm->addr_bits;

  vm->instr_bits  = 3u * vm->addr_bits;
  vm->instr_bytes = vm->instr_bits / 8u;

  vm->processor_start = 0;
  vm->processor_bits  = (bitaddr_t)vm->processor_n * (bitaddr_t)vm->instr_bits;

  vm->off_n   = 0;
  vm->off_dst = vm->n_bits;
  vm->off_src = vm->n_bits + vm->addr_bits;

  /* sanity: processor must fit */
  if (vm->processor_bits > vm->space_bits) { vm_free(vm); return -1; }

  vm_compute_mmio_layout(vm);

  /* sanity: mmio must fit */
  if (vm->mmio.end > vm->space_bits) { vm_free(vm); return -1; }

  return 0;
}

void vm_free(vm_t *vm) {
  if (!vm) return;
  free(vm->space);
  memset(vm, 0, sizeof *vm);
}

/* -------- MMIO handshake service --------
 *
 * Semantics:
 * - The device checks *_REQ at the start of the tick.
 * - If REQ=1:
 *     - clears DONE/ERR/(EOF) and GOT
 *     - performs the operation (byte-aligned)
 *     - writes GOT, sets DONE=1 and (if needed) EOF/ERR
 *     - clears REQ=0
 * - DONE remains 1 until the program overwrites it via copy (if it wants to).
 */

static int service_in(vm_t *vm, FILE *in) {
  if (!vm_bit_get(vm, vm->mmio.in_req)) return 0;

  /* clear status */
  vm_bit_set(vm, vm->mmio.in_done, 0);
  vm_bit_set(vm, vm->mmio.in_eof,  0);
  vm_bit_set(vm, vm->mmio.in_err,  0);
  vm_write_uint(vm, vm->mmio.in_got, vm->n_bits, 0);

  uint64_t dst = vm_read_uint(vm, vm->mmio.in_dst, vm->addr_bits);
  uint64_t len = vm_read_uint(vm, vm->mmio.in_len, vm->n_bits);

  /* require byte alignment */
  if ((dst & 7u) || (len & 7u)) {
    vm_bit_set(vm, vm->mmio.in_err, 1);
    vm_bit_set(vm, vm->mmio.in_done, 1);
    vm_bit_set(vm, vm->mmio.in_req, 0);
    return 0;
  }

  bitaddr_t bd = (bitaddr_t)dst;
  bitaddr_t bl = (bitaddr_t)len;

  if (bd + bl > vm->space_bits) {
    vm_bit_set(vm, vm->mmio.in_err, 1);
    vm_bit_set(vm, vm->mmio.in_done, 1);
    vm_bit_set(vm, vm->mmio.in_req, 0);
    return 0;
  }

  size_t nbytes = (size_t)(bl >> 3);
  size_t byte_dst = (size_t)(bd >> 3);

  size_t got = 0;
  if (nbytes) {
    got = fread(&vm->space[byte_dst], 1, nbytes, in);
    if (got == 0 && feof(in)) vm_bit_set(vm, vm->mmio.in_eof, 1);
    if (ferror(in)) vm_bit_set(vm, vm->mmio.in_err, 1);
  }

  vm_write_uint(vm, vm->mmio.in_got, vm->n_bits, (uint64_t)got * 8u);
  vm_bit_set(vm, vm->mmio.in_done, 1);
  vm_bit_set(vm, vm->mmio.in_req, 0);
  return 0;
}

static int service_out(vm_t *vm, FILE *out) {
  if (!vm_bit_get(vm, vm->mmio.out_req)) return 0;

  vm_bit_set(vm, vm->mmio.out_done, 0);
  vm_bit_set(vm, vm->mmio.out_err,  0);
  vm_write_uint(vm, vm->mmio.out_got, vm->n_bits, 0);

  uint64_t src = vm_read_uint(vm, vm->mmio.out_src, vm->addr_bits);
  uint64_t len = vm_read_uint(vm, vm->mmio.out_len, vm->n_bits);

  if ((src & 7u) || (len & 7u)) {
    vm_bit_set(vm, vm->mmio.out_err, 1);
    vm_bit_set(vm, vm->mmio.out_done, 1);
    vm_bit_set(vm, vm->mmio.out_req, 0);
    return 0;
  }

  bitaddr_t bs = (bitaddr_t)src;
  bitaddr_t bl = (bitaddr_t)len;

  if (bs + bl > vm->space_bits) {
    vm_bit_set(vm, vm->mmio.out_err, 1);
    vm_bit_set(vm, vm->mmio.out_done, 1);
    vm_bit_set(vm, vm->mmio.out_req, 0);
    return 0;
  }

  size_t nbytes = (size_t)(bl >> 3);
  size_t byte_src = (size_t)(bs >> 3);

  size_t put = 0;
  if (nbytes) {
    put = fwrite(&vm->space[byte_src], 1, nbytes, out);
    if (put != nbytes) vm_bit_set(vm, vm->mmio.out_err, 1);
    fflush(out);
  }

  vm_write_uint(vm, vm->mmio.out_got, vm->n_bits, (uint64_t)put * 8u);
  vm_bit_set(vm, vm->mmio.out_done, 1);
  vm_bit_set(vm, vm->mmio.out_req, 0);
  return 0;
}

/* -------- execution -------- */

vm_rc_t vm_tick(vm_t *vm, FILE *in, FILE *out) {
  if (!vm || !vm->space) return VM_ERR;

  /* diagnostics: reset last_err for this tick */
  vm->last_err.kind = VM_E_NONE;
  vm->last_err.tick = vm->tick_counter;
  vm->last_err.slot = 0;
  vm->last_err.ins  = (vm_inst_t){0,0,0};
  vm->last_err.space_bits = vm->space_bits;


  /* 1) MMIO at start of tick */
  if (service_out(vm, out) != 0) return VM_ERR;
  if (service_in(vm, in) != 0) return VM_ERR;

  /* 2) HALT check after I/O (allows "print first, then stop") */
  if (vm_bit_get(vm, vm->mmio.halt)) { vm->tick_counter++; return VM_HALT; }

  /* 3) fetch-execute slots */
  if (vm->hooks.tick_begin) vm->hooks.tick_begin(vm->hooks.user, vm->processor_n);
  for (unsigned i = 0; i < vm->processor_n; i++) {
    bitaddr_t ip = vm_proc_slot_ip(vm, i);
    vm_inst_t ins = vm_read_inst(vm, ip);

    if (ins.n == 0) continue; /* NOP */

    bitaddr_t n   = (bitaddr_t)ins.n;
    bitaddr_t src = (bitaddr_t)ins.src;
    bitaddr_t dst = (bitaddr_t)ins.dst;

    if (src + n > vm->space_bits) {
      vm->last_err.kind = VM_E_SRC_BOUNDS;
      vm->last_err.tick = vm->tick_counter;
      vm->last_err.slot = i;
      vm->last_err.ins  = ins;
      vm->last_err.space_bits = vm->space_bits;
      fprintf(stderr,
              "VM_ERR: tick=%" PRIu64 " slot=%u n=%" PRIu64 " dst=%" PRIu64 " src=%" PRIu64 " kind=%d space_bits=%" PRIu64 "\n",
              (uint64_t)vm->last_err.tick,
              (unsigned)vm->last_err.slot,
              (uint64_t)vm->last_err.ins.n,
              (uint64_t)vm->last_err.ins.dst,
              (uint64_t)vm->last_err.ins.src,
              (int)vm->last_err.kind,
              (uint64_t)vm->last_err.space_bits);
      return VM_ERR;
    }
    if (dst + n > vm->space_bits) {
      vm->last_err.kind = VM_E_DST_BOUNDS;
      vm->last_err.tick = vm->tick_counter;
      vm->last_err.slot = i;
      vm->last_err.ins  = ins;
      vm->last_err.space_bits = vm->space_bits;
      fprintf(stderr,
              "VM_ERR: tick=%" PRIu64 " slot=%u n=%" PRIu64 " dst=%" PRIu64 " src=%" PRIu64 " kind=%d space_bits=%" PRIu64 "\n",
              (uint64_t)vm->last_err.tick,
              (unsigned)vm->last_err.slot,
              (uint64_t)vm->last_err.ins.n,
              (uint64_t)vm->last_err.ins.dst,
              (uint64_t)vm->last_err.ins.src,
              (int)vm->last_err.kind,
              (uint64_t)vm->last_err.space_bits);
      return VM_ERR;
    }

    /* bitcpy uses size_t offsets; with 512KB this is safe */
    if (vm->hooks.note_copy) vm->hooks.note_copy(vm->hooks.user, (uint64_t)dst, (uint64_t)n, (uint64_t)src);

    bitcpy((size_t)n, vm->space, (size_t)src, vm->space, (size_t)dst);
  }


  if (vm->hooks.tick_end) vm->hooks.tick_end(vm->hooks.user);


  vm->tick_counter++;

  return VM_OK;
}

vm_rc_t vm_run(vm_t *vm, uint64_t life, FILE *in, FILE *out) {
  while (life--) {
    vm_rc_t rc = vm_tick(vm, in, out);
    if (rc != VM_OK) return rc;
  }
  return VM_OK;
}

/* -------- build boot loader layer (pure copycode image) -------- */

static void clear_processor(vm_t *vm) {
  for (unsigned i = 0; i < vm->processor_n; i++) {
    vm_write_inst(vm, vm_proc_slot_ip(vm, i), (vm_inst_t){0,0,0});
  }
}

int vm_build_boot_loader_layer(vm_t *vm, bitaddr_t next_layer_ptr) {
  if (!vm) return -1;

  /* next_layer_ptr must fit in addr_bits */
  if (next_layer_ptr >= ((bitaddr_t)1u << vm->addr_bits)) return -1;

  clear_processor(vm);

  /* slot0: NOP but carries pointer in dst field */
  vm_inst_t meta = { .n = 0, .dst = (uint64_t)next_layer_ptr, .src = 0 };
  vm_write_inst(vm, vm_proc_slot_ip(vm, 0), meta);

  unsigned patch_slot = vm->processor_n - 2;
  unsigned load_slot  = vm->processor_n - 1;

  /* patch: copy ADDR_BITS into src-field of load_slot from dst-field of slot0 */
  bitaddr_t src_field_of_load = vm_proc_slot_field_ip(vm, load_slot, vm->off_src);
  bitaddr_t dst_field_of_slot0 = vm_proc_slot_field_ip(vm, 0, vm->off_dst);

  vm_inst_t patch = {
    .n   = vm->addr_bits,
    .dst = (uint64_t)src_field_of_load,
    .src = (uint64_t)dst_field_of_slot0
  };

  /* load: copy PROCESSOR_BITS into processor_start; src will be patched */
  vm_inst_t load = {
    .n   = (uint64_t)vm->processor_bits,
    .dst = (uint64_t)vm->processor_start,
    .src = 0
  };

  vm_write_inst(vm, vm_proc_slot_ip(vm, patch_slot), patch);
  vm_write_inst(vm, vm_proc_slot_ip(vm, load_slot),  load);

  return 0;
}
