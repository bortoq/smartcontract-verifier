/* invariants.h — optional runtime invariants (opt-in checks)
 *
 * These checks are intended for debugging and CI hardening.
 * They are not required for the baseline workflow.
 */
#ifndef COPYSPACE_INVARIANTS_H_
#define COPYSPACE_INVARIANTS_H_

#include "space.h"

/* Strict alignment / safety checks for std7_fixed pointer regs (VAR_AP/BP/RP).
 * Returns 0 on success, -1 on invariant violation (and prints VM_ERR).
 */
int vm_invariants_strict_align32_check(vm_t *vm);

#endif
