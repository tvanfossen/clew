# SPDX-License-Identifier: MIT
"""Interrupt handlers recognised at their DEFINITION rather than at a registration call.

gh#47 part 1. The registration half lives in `threads.DEFAULT_SPAWN_PATTERNS`: a call whose Nth
argument is the handler. That half cannot see the firmware majority, because most handlers are
never passed to anything — the vector table is in assembly, or generated at build time, and the
C side is a definition the LINKER resolves by name. Measured at pinned commits:

  * RIOT 50ae2eba: 127 `void isr_<periph>(void)` definitions overriding `WEAK_DEFAULT` aliases,
    15 `__attribute__((interrupt("IRQ")))` on lpc23xx/arm7, 12 msp430 `ISR(VECTOR, name)`.
  * FreeRTOS demos 202411.00: 882 `*_IRQHandler`, 163 CMSIS core `*_Handler`, 100
    `vApplicationTickHook`, 12 `vApplication(FPUSafe)IRQHandler`.
  * Zephyr v4.4.2: 22 `ISR_DIRECT_DECLARE(name)`, whose argument BECOMES the function name
    (ARCH_ISR_DIRECT_DECLARE, include/zephyr/arch/arm/irq.h:202-213).

THREE FORMS, TWO STRENGTHS. An interrupt attribute and a handler-declaring macro are what the
SOURCE SAYS; a name ending in `_IRQHandler` is what this module INFERRED. They are recorded
under different `threads.source` values rather than merged, because a reader weighing a context
conflict needs to know which one it rests on.

WHAT IS REFUSED, and why each refusal is a measurement and not an oversight:

  * `Reset_Handler` / `ResetISR` / `__iar_program_start` — they satisfy the naming convention and
    call `main()`. Admitting them makes every blocking call in the program interrupt-reachable.
  * a glob-matched name whose definition TAKES ARGUMENTS — in RIOT that shape is a helper the
    real handler calls (`isr_handler(msp_port_isr_t *, ...)`, cpu/msp430/periph/gpio.c:213), and
    a vector handler takes none.
  * avr-libc's `ISR(TIMER1_OVF_vect)` — the argument names a VECTOR, and the symbol the macro
    defines is `__vector_13`. Nothing in the source names a function, so there is nothing to
    resolve; RIOT's own `AVR8_ISR(VECTOR, handler)` passes the handler as an argument and is
    matched by the registration half instead.

@brief Definition-site interrupt-handler detection.
@version 1
"""

from __future__ import annotations

from fnmatch import fnmatchcase
from typing import Any

## Handler-declaring macros written WHERE A FUNCTION DEFINITION GOES, whose first argument
## becomes the defined function's name. tree-sitter parses `ISR_DIRECT_DECLARE(uart_isr) { }`
## as a function_definition whose `type` is the macro name and whose declarator is a
## parenthesised declarator holding the real name.
ISR_DEFINING_MACROS = frozenset({"ISR_DIRECT_DECLARE", "ISR_DIRECT_PM"})

## Tokens that say "this definition runs in interrupt context" in its own declaration
## specifiers. `__interrupt` is the IAR/TI keyword, `__irq` the ARM compiler's.
ISR_ATTRIBUTE_TOKENS = (
    "__attribute__((interrupt",
    "__attribute__ ((interrupt",
    "__interrupt",
    "__irq",
)

## Names that ARE handlers, whatever their signature: the CMSIS core exceptions and the RTOS
## hooks whose own documentation puts them in interrupt context (FreeRTOS task.h:2052 for the
## tick hook; portable/GCC/ARM_CA9/port.c:170-186 for the Cortex-A IRQ hooks).
ISR_EXACT_NAMES = frozenset(
    {
        "NMI_Handler",
        "HardFault_Handler",
        "MemManage_Handler",
        "BusFault_Handler",
        "UsageFault_Handler",
        "DebugMon_Handler",
        "SVC_Handler",
        "PendSV_Handler",
        "SysTick_Handler",
        "vPortSVCHandler",
        "xPortPendSVHandler",
        "xPortSysTickHandler",
        "vApplicationTickHook",
        "vApplicationIRQHandler",
        "vApplicationFPUSafeIRQHandler",
        "freertos_risc_v_application_interrupt_handler",
        "freertos_risc_v_application_exception_handler",
    }
)

## Name SHAPES, matched only on a definition that takes no arguments. `*_IRQHandler` is the
## CMSIS vendor convention; `isr_*` is RIOT's Cortex-M spelling.
ISR_NAME_GLOBS = ("*_IRQHandler", "isr_*")

## Names that match a shape above and are NOT interrupt handlers. The reset entry is the one
## that matters: it calls main().
NOT_AN_ISR = frozenset(
    {"Reset_Handler", "ResetISR", "Default_Reset_Handler", "__iar_program_start"}
)

## `threads.source` for a handler the SOURCE declares (attribute or defining macro), and for one
## recognised by NAME alone. Two values because they are two strengths of evidence.
ISR_SOURCE_DECLARED = "ast_isr_decl"
ISR_SOURCE_NAMED = "ast_isr_name"


## @brief The identifier a (possibly parenthesised or pointer) declarator declares.
## @param node A declarator node, or None.
## @param src The file's raw bytes.
## @return The declared name, or "".
## @version 2
## @dg_internal
def _declared_name(node: Any, src: bytes) -> str:
    """Walks down through `function_declarator` / `parenthesized_declarator` /
    `pointer_declarator` to the identifier, which is where a macro-wrapped definition keeps the
    real name.

    @brief Read a declarator's identifier.
    @return The name, or "".
    @version 1
    """
    current = node
    while current is not None and current.type != "identifier":
        nxt = current.child_by_field_name("declarator")
        if nxt is None:
            nxt = next((c for c in current.named_children if c.type.endswith("declarator")), None)
        if nxt is None:
            nxt = next((c for c in current.named_children if c.type == "identifier"), None)
        current = nxt
    return (
        src[current.start_byte : current.end_byte].decode("utf-8", errors="replace")
        if current
        else ""
    )


## @brief Whether a function definition declares no parameters.
## @param node A `function_definition` node.
## @param src The file's raw bytes.
## @return True when the parameter list is empty or `(void)`.
## @version 1
## @dg_internal
def _takes_no_parameters(node: Any, src: bytes) -> bool:
    """A vector handler takes none. A same-shaped name that takes one is a helper the handler
    calls, which is a different claim about execution context.

    @brief Test for an empty or `(void)` parameter list.
    @return True when the definition takes nothing.
    @version 1
    """
    declarator = node.child_by_field_name("declarator")
    params = None
    while declarator is not None and params is None:
        params = declarator.child_by_field_name("parameters")
        declarator = declarator.child_by_field_name("declarator")
    if params is None:
        return False
    text = src[params.start_byte : params.end_byte].decode("utf-8", errors="replace")
    return text.replace(" ", "") in ("()", "(void)")


## @brief The interrupt-handler evidence a function definition carries, if any.
## @param node A `function_definition` node.
## @param src The file's raw bytes.
## @return (entry name, `threads.source` value), or None when it is not a handler.
## @version 2
## @req REQ-DDB-SCHEMA-001
def isr_definition(node: Any, src: bytes) -> tuple[str, str] | None:
    """Ordered by strength: the attribute and the defining macro are read off the source, the
    name conventions are an inference and are labelled as one.

    @brief Classify one function definition as an interrupt handler.
    @return (entry, source) or None.
    @version 1
    """
    declarator = node.child_by_field_name("declarator")
    name = _declared_name(declarator, src)
    if not name or name in NOT_AN_ISR:
        return None
    header = src[node.start_byte : (declarator.start_byte if declarator else node.end_byte)]
    header_text = header.decode("utf-8", errors="replace")
    if any(token in header_text for token in ISR_ATTRIBUTE_TOKENS):
        return (name, ISR_SOURCE_DECLARED)
    type_node = node.child_by_field_name("type")
    macro = (
        src[type_node.start_byte : type_node.end_byte].decode("utf-8", errors="replace")
        if type_node
        else ""
    )
    if macro in ISR_DEFINING_MACROS:
        return (name, ISR_SOURCE_DECLARED)
    if name in ISR_EXACT_NAMES:
        return (name, ISR_SOURCE_NAMED)
    if any(fnmatchcase(name, glob) for glob in ISR_NAME_GLOBS) and _takes_no_parameters(node, src):
        return (name, ISR_SOURCE_NAMED)
    return None


## @brief Count interrupt registrations written INSIDE a macro body.
## @param tree The parsed tree.
## @param src The file's raw bytes.
## @param spellings The registration callee names this build matches.
## @return How many registration spellings appear inside preprocessor definitions.
## @version 1
## @req REQ-DDB-SCHEMA-001
def count_macro_body_registrations(tree: Any, src: bytes, spellings: frozenset[str]) -> int:
    """THE ONE NUMBER THAT MAKES A ZERO HONEST. tree-sitter exposes a `#define` body as opaque
    text, so a registration written inside one is not a call node and no call-site matcher can
    see it — and Zephyr writes 718 of its 1110 `IRQ_CONNECT` sites that way (64.7%; 69.0% under
    drivers/), because a driver instantiates itself once per devicetree node through
    `DT_INST_FOREACH_STATUS_OKAY`.

    Reporting `0 interrupt handlers` on such a tree would be a measured-looking claim about a
    tree the layer could not read. This counts what it could not read, by TEXT, and claims
    nothing more: no handler name is recovered, because 46 of those sites name a macro
    parameter or a token-pasted identifier that exists only after preprocessing.

    @brief Count registrations hidden in macro bodies.
    @return The count.
    @version 1
    """
    found = 0
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type not in ("preproc_def", "preproc_function_def"):
            continue
        value = node.child_by_field_name("value")
        if value is None:
            continue
        text = src[value.start_byte : value.end_byte].decode("utf-8", errors="replace")
        found += sum(1 for name in spellings if f"{name}(" in text.replace(" (", "("))
    return found
