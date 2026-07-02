/* invariants.c — optional runtime invariants (opt-in checks)
 */
#include "invariants.h"
#include <inttypes.h>
#include <stdarg.h>
#include <stdio.h>

static bitaddr_t align8_bits(bitaddr_t x) { return (x + 7u) & ~(bitaddr_t)7u; }

static int invariant_fail(vm_t *vm, const char *fmt, ...) {
  if (!vm) return -1;

  vm->last_err.kind = VM_E_ALIGN32;
  vm->last_err.tick = vm->tick_counter;
  vm->last_err.slot = 0;
  vm->last_err.ins  = (vm_inst_t){0,0,0};
  vm->last_err.space_bits = vm->space_bits;

  va_list ap;
  va_start(ap, fmt);
  vfprintf(stderr, fmt, ap);
  va_end(ap);

  return -1;
}

static int check_var_ptr(vm_t *vm, const char *name, bitaddr_t var_addr, uint64_t min_bits) {
  uint64_t v = vm_read_uint(vm, var_addr, vm->addr_bits);

  /* allow null pointers: before program init, VAR_* may be 0 */
  if (v == 0ull) return 0;

  uint64_t sb = (uint64_t)vm->space_bits;
  uint64_t wb = (uint64_t)vm->workspace_base;

  if (v >= sb || v + min_bits > sb) {
    return invariant_fail(
      vm,
      "VM_ERR: tick=%" PRIu64 " kind=%d %s=%" PRIu64 " is out of bounds (space_bits=%" PRIu64 ", min_bits=%" PRIu64 ")\n",
      (uint64_t)vm->tick_counter,
      (int)VM_E_ALIGN32,
      name,
      (uint64_t)v,
      (uint64_t)vm->space_bits,
      (uint64_t)min_bits
    );
  }

  if ((v & 31ull) != 0ull) {
    return invariant_fail(
      vm,
      "VM_ERR: tick=%" PRIu64 " kind=%d %s=%" PRIu64 " (at bitaddr=%" PRIu64 ") is not 32-bit aligned (bitaddr%%32!=0)\n",
      (uint64_t)vm->tick_counter,
      (int)VM_E_ALIGN32,
      name,
      (uint64_t)v,
      (uint64_t)var_addr
    );
  }

  if (v < wb) {
    return invariant_fail(
      vm,
      "VM_ERR: tick=%" PRIu64 " kind=%d %s=%" PRIu64 " is in processor/MMIO region (workspace_base=%" PRIu64 ")\n",
      (uint64_t)vm->tick_counter,
      (int)VM_E_ALIGN32,
      name,
      (uint64_t)v,
      (uint64_t)vm->workspace_base
    );
  }

  return 0;
}

static int check_rp_protected(vm_t *vm,
                              uint64_t rp,
                              bitaddr_t protected_begin,
                              bitaddr_t protected_end,
                              bitaddr_t var_ap_addr,
                              bitaddr_t var_bp_addr,
                              bitaddr_t var_rp_addr,
                              unsigned width) {
  if (rp == 0ull) return 0;

  if (rp >= (uint64_t)protected_begin && rp < (uint64_t)protected_end) {
    return invariant_fail(
      vm,
      "VM_ERR: tick=%" PRIu64 " kind=%d VAR_RP=%" PRIu64 " is in protected region (begin=%" PRIu64 " end=%" PRIu64 ")\n",
      (uint64_t)vm->tick_counter,
      (int)VM_E_ALIGN32,
      (uint64_t)rp,
      (uint64_t)protected_begin,
      (uint64_t)protected_end
    );
  }

  /* Also protect the VAR_* cells themselves (writes here corrupt pointers). */
  if (rp >= (uint64_t)var_ap_addr && rp < (uint64_t)(var_ap_addr + (bitaddr_t)width)) {
    return invariant_fail(
      vm,
      "VM_ERR: tick=%" PRIu64 " kind=%d VAR_RP=%" PRIu64 " points into VAR_AP cell\n",
      (uint64_t)vm->tick_counter,
      (int)VM_E_ALIGN32,
      (uint64_t)rp
    );
  }
  if (rp >= (uint64_t)var_bp_addr && rp < (uint64_t)(var_bp_addr + (bitaddr_t)width)) {
    return invariant_fail(
      vm,
      "VM_ERR: tick=%" PRIu64 " kind=%d VAR_RP=%" PRIu64 " points into VAR_BP cell\n",
      (uint64_t)vm->tick_counter,
      (int)VM_E_ALIGN32,
      (uint64_t)rp
    );
  }
  if (rp >= (uint64_t)var_rp_addr && rp < (uint64_t)(var_rp_addr + (bitaddr_t)width)) {
    return invariant_fail(
      vm,
      "VM_ERR: tick=%" PRIu64 " kind=%d VAR_RP=%" PRIu64 " points into VAR_RP cell\n",
      (uint64_t)vm->tick_counter,
      (int)VM_E_ALIGN32,
      (uint64_t)rp
    );
  }

  return 0;
}

int vm_invariants_strict_align32_check(vm_t *vm) {
  if (!vm) return -1;

  const unsigned width = vm->addr_bits;

  /* std7_fixed legacy: ART base is computed relative to workspace_base */
  const bitaddr_t ART = align8_bits(vm->workspace_base + 512u);

  const bitaddr_t need_end = ART + (bitaddr_t)(61u) * (bitaddr_t)width;
  if (need_end > vm->space_bits) {
    return invariant_fail(
      vm,
      "VM_ERR: tick=%" PRIu64 " kind=%d cannot locate ART (out of bounds)\n",
      (uint64_t)vm->tick_counter,
      (int)VM_E_ALIGN32
    );
  }

  bitaddr_t var_ap_addr = (bitaddr_t)vm_read_uint(vm, ART + (bitaddr_t)58u * (bitaddr_t)width, width);
  bitaddr_t var_bp_addr = (bitaddr_t)vm_read_uint(vm, ART + (bitaddr_t)59u * (bitaddr_t)width, width);
  bitaddr_t var_rp_addr = (bitaddr_t)vm_read_uint(vm, ART + (bitaddr_t)60u * (bitaddr_t)width, width);

  if (var_ap_addr + width > vm->space_bits) {
    return invariant_fail(
      vm,
      "VM_ERR: tick=%" PRIu64 " kind=%d VAR_AP addr out of bounds\n",
      (uint64_t)vm->tick_counter, (int)VM_E_ALIGN32
    );
  }
  if (var_bp_addr + width > vm->space_bits) {
    return invariant_fail(
      vm,
      "VM_ERR: tick=%" PRIu64 " kind=%d VAR_BP addr out of bounds\n",
      (uint64_t)vm->tick_counter, (int)VM_E_ALIGN32
    );
  }
  if (var_rp_addr + width > vm->space_bits) {
    return invariant_fail(
      vm,
      "VM_ERR: tick=%" PRIu64 " kind=%d VAR_RP addr out of bounds\n",
      (uint64_t)vm->tick_counter, (int)VM_E_ALIGN32
    );
  }

  /* LOAD24 and STORE24 access 24 bits starting at the pointer bitaddr. */
  const uint64_t need_bits = 24ull;

  if (check_var_ptr(vm, "VAR_AP", var_ap_addr, need_bits) != 0) return -1;
  if (check_var_ptr(vm, "VAR_BP", var_bp_addr, need_bits) != 0) return -1;
  if (check_var_ptr(vm, "VAR_RP", var_rp_addr, need_bits) != 0) return -1;

  /* Protected write region for RP: keep stacks away from ART and related tables. */
  {
    uint64_t rp = vm_read_uint(vm, var_rp_addr, width);
    bitaddr_t protected_begin = vm->workspace_base;
    bitaddr_t protected_end = need_end;
    if (check_rp_protected(vm, rp, protected_begin, protected_end, var_ap_addr, var_bp_addr, var_rp_addr, width) != 0) return -1;
  }

  return 0;
}
