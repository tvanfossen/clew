/* Gating fixture for gh#18 part 3. Every conditional shape the harvest claims to
 * read appears exactly once, so a test can assert the FORM as well as the line. */

#include <stddef.h>

#ifdef CONFIG_WIDGET_MOTOR_BETA
void motor_beta_init(void) {}
#endif

#ifndef CONFIG_WIDGET_RADIO
void radio_stub(void) {}
#endif

#if defined(CONFIG_WIDGET_MOTOR_ALPHA) || CONFIG_WIDGET_LOG_LEVEL > 2
void motor_alpha_trace(void) {}
#endif

/* A gate on a symbol NO Kconfig declares: dead code behind a switch nobody can
 * set. The harvest keeps it deliberately — filtering to declared symbols would
 * delete the evidence of the defect. */
#ifdef CONFIG_WIDGET_UNDECLARED
void orphan_gate(void) {}
#endif

/* A runtime branch, NOT a gate. The code is compiled either way, so recording it
 * as gating would tell a reader that removing the symbol removes the function. */
void motor_poll(void)
{
	if (IS_ENABLED(CONFIG_WIDGET_RADIO)) {
		return;
	}
}
