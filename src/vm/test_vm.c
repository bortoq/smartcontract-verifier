/**
 * test_vm.c — VM runtime smoke tests.
 *
 * Tests:
 *   test1: basic copy — copy 8 bits from byte 100 to byte 200
 *   test2: NOP — instruction with n=0 does nothing
 *   test3: multiple slots — two independent copies in one tick
 *   test4: MMIO HALT — setting HALT bit stops execution
 */
#include <stdio.h>
#include <string.h>
#include "space.h"

#ifndef VM_SPACE_BYTES
#define VM_SPACE_BYTES (512u * 1024u)
#endif
#ifndef VM_PROCESSOR_N
#define VM_PROCESSOR_N 64u
#endif

static int test_count = 0;
static int pass_count = 0;

static void check(int cond, const char *name) {
    test_count++;
    printf("  %s: %s\n", cond ? "PASS" : "FAIL", name);
    if (cond) pass_count++;
}

int main(void) {
    vm_t vm;

    /* ── test1: basic copy ── */
    printf("test1: basic copy\n");
    memset(&vm, 0, sizeof(vm));
    if (vm_init(&vm, VM_SPACE_BYTES, VM_PROCESSOR_N)) return 1;
    memset(vm.space, 0, vm.space_bytes);

    vm_inst_t ins = { .n = 8, .dst = 1600, .src = 800 };
    vm_write_inst(&vm, vm_proc_slot_ip(&vm, 0), ins);
    vm.space[100] = 0xAA;

    vm_rc_t rc = vm_tick(&vm, NULL, NULL);
    check(rc == VM_OK, "vm_tick returns VM_OK");
    check(vm.space[200] == 0xAA, "copy(8, dst=1600, src=800) copies byte correctly");

    vm_free(&vm);

    /* ── test2: NOP (n=0) does nothing ── */
    printf("test2: NOP\n");
    if (vm_init(&vm, VM_SPACE_BYTES, VM_PROCESSOR_N)) return 1;
    memset(vm.space, 0, vm.space_bytes);
    vm.space[100] = 0xBB;

    /* slot 0: NOP */
    vm_inst_t nop = { .n = 0, .dst = 0, .src = 0 };
    vm_write_inst(&vm, vm_proc_slot_ip(&vm, 0), nop);
    vm.space[200] = 0x00;

    rc = vm_tick(&vm, NULL, NULL);
    check(rc == VM_OK, "vm_tick returns VM_OK");
    check(vm.space[200] == 0x00, "NOP does not change memory");

    vm_free(&vm);

    /* ── test3: multiple independent copies ── */
    printf("test3: multiple slots\n");
    if (vm_init(&vm, VM_SPACE_BYTES, VM_PROCESSOR_N)) return 1;
    memset(vm.space, 0, vm.space_bytes);

    vm.space[100] = 0x11;
    vm.space[101] = 0x22;

    /* slot 0: copy(8, dst=1600, src=800) — byte 100 → byte 200 */
    vm_write_inst(&vm, vm_proc_slot_ip(&vm, 0),
                  (vm_inst_t){ .n = 8, .dst = 1600, .src = 800 });
    /* slot 1: copy(8, dst=1800, src=808) — byte 101 → byte 225 */
    vm_write_inst(&vm, vm_proc_slot_ip(&vm, 1),
                  (vm_inst_t){ .n = 8, .dst = 1800, .src = 808 });

    vm.space[200] = 0x00;
    vm.space[225] = 0x00;

    rc = vm_tick(&vm, NULL, NULL);
    check(rc == VM_OK, "vm_tick returns VM_OK");
    check(vm.space[200] == 0x11, "slot 0 copy correct");
    check(vm.space[225] == 0x22, "slot 1 copy correct");

    vm_free(&vm);

    /* ── test4: MMIO HALT ── */
    printf("test4: HALT\n");
    if (vm_init(&vm, VM_SPACE_BYTES, VM_PROCESSOR_N)) return 1;
    memset(vm.space, 0, vm.space_bytes);

    /* Write instruction */
    vm.space[100] = 0x33;
    vm_write_inst(&vm, vm_proc_slot_ip(&vm, 0),
                  (vm_inst_t){ .n = 8, .dst = 1600, .src = 800 });

    /* Set HALT bit (mmio.halt = 4759) */
    vm_bit_set(&vm, vm.mmio.halt, 1);

    rc = vm_tick(&vm, NULL, NULL);
    check(rc == VM_HALT, "vm_tick returns VM_HALT when HALT bit is set");
    check(vm.space[200] == 0x00, "copy was not executed (halted before execution)");

    vm_free(&vm);

    /* ── summary ── */
    printf("\n%d/%d passed\n", pass_count, test_count);
    return pass_count == test_count ? 0 : 1;
}
