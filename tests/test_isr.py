# SPDX-License-Identifier: MIT
"""gh#47 part 1: an interrupt handler is an execution context, not an unreferenced function.

The spellings here were read off three firmware trees at pinned commits (RIOT 50ae2eba,
Zephyr v4.4.2, FreeRTOS-Kernel V11.3.1 with the 202411.00 demos), not off documentation:

  * Zephyr registers by CALL — `IRQ_CONNECT(irq, prio, isr, arg, flags)` — 1110 sites, and
    documents a second family whose CALLBACK runs in interrupt context (`k_timer_init`'s
    expiry function, `gpio_init_callback`'s handler, the uart/can/ipm callbacks).
  * RIOT mostly DEFINES its handlers: `isr_uart0`, `AVR8_ISR(VECTOR, handler)`,
    `ISR(VECTOR, name)`, `__attribute__((interrupt("IRQ")))`.
  * Linux passes the handler to `request_irq`, and `request_threaded_irq` passes TWO — a hard
    handler that runs in interrupt context and a thread_fn that does not.

@brief Tests for ISR execution-context detection.
@version 1
"""

from __future__ import annotations

import pytest

from clew.harvest import try_import_tree_sitter
from clew.threads import (
    DEFAULT_SPAWN_PATTERNS,
    _walk_spawn_sites,
    load_thread_patterns,
    patterns_by_name,
)

pytestmark = pytest.mark.skipif(
    try_import_tree_sitter() is None,
    reason="the ISR tests need tree_sitter + its C grammar",
)

## The septet `_walk_spawn_sites` emits, read by meaning rather than by index literal.
NAME, ENTRY, KIND, QUALIFIED, SEP, LINE, ENCLOSING, SOURCE = range(8)


## @brief Harvest spawn/ISR sites from one C source blob with the DEFAULT patterns.
## @param src Source bytes.
## @return Harvested site records.
## @version 1
def _sites(src: bytes) -> list[list]:
    """@brief Walk one C blob with the shipped pattern set."""
    import tree_sitter_c
    from tree_sitter import Language, Parser

    parser = Parser(Language(tree_sitter_c.language()))
    return _walk_spawn_sites(parser.parse(src), src, patterns_by_name(load_thread_patterns(None)))


_REGISTRATIONS = b"""\
void timer_isr(const void *arg);
void dma_isr(void *arg);
void gpio_isr(void *arg);
void hard_isr(int irq, void *dev);
void work_thread(int irq, void *dev);
void on_int(int sig);
void expiry(struct k_timer *t);
void button_pressed(const struct device *port, struct gpio_callback *cb, uint32_t pins);

static int setup(const struct device *dev, int irq, struct gpio_callback *cb)
{
    IRQ_CONNECT(irq, 1, timer_isr, DEVICE_DT_INST_GET(0), 0);
    esp_intr_alloc(ETS_GPIO_INTR_SOURCE, 0, dma_isr, NULL, NULL);
    gpio_isr_handler_add(4, gpio_isr, NULL);
    request_threaded_irq(irq, hard_isr, work_thread, 0, "dev", dev);
    signal(SIGINT, on_int);
    signal(SIGTERM, SIG_IGN);
    k_timer_init(&timer, expiry, NULL);
    gpio_init_callback(cb, button_pressed, BIT(3));
    return 0;
}
"""


def test_registration_calls_are_isr_entries() -> None:
    """THE SHIPPED SET, not a declaration. The acceptance targets for this feature build with
    `declare: {}` on purpose — a rubric that declares the patterns grades the declaration, not
    the index — so an ISR spelling that is declarable-only contributes nothing where it counts.

    `k_timer_init` and `gpio_init_callback` are in the same list for the same reason as
    `IRQ_CONNECT`: Zephyr documents both callbacks as running in interrupt context
    (include/zephyr/kernel.h:1861-1864 for the timer expiry function;
    include/zephyr/drivers/gpio/gpio_utils.h:139 dispatches the GPIO handler from the
    controller's ISR). The context is what the layer models, not the vector.

    @brief Interrupt registrations are harvested as kind 'isr'.
    @version 1
    """
    sites = _sites(_REGISTRATIONS)
    found = {site[ENTRY]: site[KIND] for site in sites}

    for entry in ("timer_isr", "dma_isr", "gpio_isr", "hard_isr", "on_int", "expiry",
                  "button_pressed"):
        assert entry in found, f"{entry} must be harvested as an interrupt entry; got {found}"
        assert found[entry] == "isr", f"{entry} runs in interrupt context, got kind {found[entry]!r}"


def test_a_threaded_irq_files_its_bottom_half_as_a_thread_not_an_isr() -> None:
    """`request_threaded_irq(irq, handler, thread_fn, ...)` registers TWO functions with two
    execution contexts: `handler` runs in hard interrupt context, `thread_fn` on a kernel
    thread created for it — where blocking is the entire point.

    ONE PATTERN PER CALLEE NAME cannot express that, which is why the pattern map is keyed to a
    LIST. Filing `thread_fn` as 'isr' would report every mutex the bottom half takes as an
    interrupt-context conflict; omitting it loses a real thread.

    @brief Both handlers of a threaded IRQ are recorded, with different kinds.
    @version 1
    """
    sites = _sites(_REGISTRATIONS)
    found = {site[ENTRY]: site[KIND] for site in sites}

    assert found.get("hard_isr") == "isr", f"the hard handler is interrupt context; got {found}"
    assert found.get("work_thread") == "task", (
        f"the threaded bottom half is a THREAD, and may block; got {found}"
    )


def test_a_sentinel_handler_is_not_a_function() -> None:
    """`signal(SIGTERM, SIG_IGN)` names no function. Recorded as written it mints a thread
    called SIG_IGN whose entry never resolves, and a NULL entry does not deduplicate — SQLite
    treats NULLs as distinct in a UNIQUE constraint — so every such site adds another row.

    The same shape appears with a deregistering registration: RIOT's
    `install_irq(RTC_INT, NULL, 1)` (cpu/lpc23xx/periph/rtc.c:191) passes NULL for the handler.

    @brief A sentinel or null handler argument records nothing.
    @version 1
    """
    entries = {site[ENTRY] for site in _sites(_REGISTRATIONS)}
    assert "SIG_IGN" not in entries, f"SIG_IGN names no function; got {sorted(entries)}"


def test_the_shipped_patterns_still_cover_the_thread_primitives() -> None:
    """The ISR entries are ADDED to the same table the thread primitives live in. A regression
    that drops pthread_create while adding IRQ_CONNECT would pass every test above.

    @brief The pre-existing spawn defaults survive.
    @version 1
    """
    by_name: dict[str, list] = {}
    for pattern in DEFAULT_SPAWN_PATTERNS:
        by_name.setdefault(pattern.name, []).append(pattern)

    for name in ("pthread_create", "xTaskCreate", "osThreadNew", "std::thread", "CreateThread"):
        assert name in by_name, f"{name} must remain a default; got {sorted(by_name)}"
    assert by_name["pthread_create"][0].entry_arg_index == 2
    assert by_name["pthread_create"][0].kind == "pthread"


_DEFINITIONS = b"""\
void tick(void);
void drain(void);
int main(void);

__attribute__((interrupt("IRQ"))) void tim0_handler(void) { tick(); }

void TIM1_IRQHandler(void) { tick(); }

void isr_uart0(void) { drain(); }

void SysTick_Handler(void) { tick(); }

void vApplicationTickHook(void) { tick(); }

ISR_DIRECT_DECLARE(uarte_isr) { drain(); }

void Reset_Handler(void) { main(); }

void isr_helper(int channel) { drain(); }

void TIM2_IRQHandler(void);
"""


def test_a_handler_declared_at_its_definition_is_an_isr_entry() -> None:
    """RIOT and FreeRTOS mostly do NOT register their handlers by call — the vector table is in
    assembly or generated at build time, and the C side is a definition the linker resolves by
    NAME. Read at their pins: 127 `isr_*` definitions in RIOT, 882 `*_IRQHandler` in the
    FreeRTOS demos, plus the CMSIS core exception names and FreeRTOS's documented hooks.

    A call-site matcher sees none of them, which is why the FreeRTOS demo scope reports ZERO
    interrupt handlers from registrations alone.

    @brief Attribute, macro-wrapper and naming definitions are harvested.
    @version 1
    """
    found = {site[ENTRY]: site for site in _sites(_DEFINITIONS)}

    for entry in ("tim0_handler", "TIM1_IRQHandler", "isr_uart0", "SysTick_Handler",
                  "vApplicationTickHook", "uarte_isr"):
        assert entry in found, f"{entry} is an interrupt handler; found {sorted(found)}"
        assert found[entry][KIND] == "isr", f"{entry} got kind {found[entry][KIND]!r}"


def test_what_the_definition_forms_refuse() -> None:
    """THE THREE REFUSALS, each measured rather than assumed.

    `Reset_Handler` satisfies the CMSIS naming convention and is the one entry that must never
    be an ISR: it calls main(), so every blocking call in the program becomes interrupt-
    reachable through it. `isr_helper(int)` is named like a handler and takes an argument — in
    RIOT that shape is a helper the real handler calls (cpu/msp430/periph/gpio.c:213), not a
    vector. A bare declaration is not a definition and names no body to walk.

    @brief A reset entry, an argument-taking lookalike and a declaration are refused.
    @version 1
    """
    entries = {site[ENTRY] for site in _sites(_DEFINITIONS)}

    assert "Reset_Handler" not in entries, "the reset entry reaches main(); it is not an ISR"
    assert "isr_helper" not in entries, "a handler-shaped name taking an argument is a helper"
    assert "TIM2_IRQHandler" not in entries, "a declaration defines no handler"


def test_a_naming_guess_is_labelled_differently_from_a_declared_interrupt() -> None:
    """`__attribute__((interrupt))` and `ISR_DIRECT_DECLARE(x)` are what the SOURCE SAYS; a name
    ending in _IRQHandler is what the index INFERRED. Both are worth recording and they are not
    the same evidence, so they are not written under the same `threads.source`.

    @brief Evidence strength rides on the source column, not on the kind.
    @version 1
    """
    found = {site[ENTRY]: site for site in _sites(_DEFINITIONS)}

    assert found["tim0_handler"][SOURCE] == "ast_isr_decl", (
        f"an interrupt attribute is declared, not guessed; got {found['tim0_handler'][SOURCE]!r}"
    )
    assert found["uarte_isr"][SOURCE] == "ast_isr_decl", (
        f"a handler-declaring macro is declared; got {found['uarte_isr'][SOURCE]!r}"
    )
    assert found["TIM1_IRQHandler"][SOURCE] == "ast_isr_name", (
        f"a naming convention is an inference; got {found['TIM1_IRQHandler'][SOURCE]!r}"
    )
    registered = {site[ENTRY]: site for site in _sites(_REGISTRATIONS)}
    assert registered["timer_isr"][SOURCE] == "ast_spawn", (
        f"a registration call is the existing source; got {registered['timer_isr'][SOURCE]!r}"
    )


def test_a_registration_inside_a_macro_body_is_counted_not_ignored() -> None:
    """THE NUMBER THAT KEEPS A ZERO HONEST. A Zephyr driver instantiates itself once per
    devicetree node, so its IRQ_CONNECT is written inside a `#define` body and expanded by
    `DT_INST_FOREACH_STATUS_OKAY`. tree-sitter exposes a macro body as opaque text — there is no
    call node to match — and at v4.4.2 that is 718 of 1110 sites (64.7%).

    Reporting "0 interrupt handlers" on such a driver would be a measured-looking claim about a
    file the layer could not read. The count says what was not read; it does NOT invent a
    handler, because 46 of those sites name a macro parameter or a token-pasted identifier that
    only exists after preprocessing.

    @brief Registrations hidden in macro bodies are counted.
    @version 1
    """
    import tree_sitter_c
    from tree_sitter import Language, Parser

    from clew.isr import count_macro_body_registrations

    src = b"""\
#define UART_INIT(n)                                                   \\
    static void uart_irq_config_##n(const struct device *dev)          \\
    {                                                                  \\
        IRQ_CONNECT(DT_INST_IRQN(n), DT_INST_IRQ(n, priority),         \\
                    uart_isr, DEVICE_DT_INST_GET(n), 0);               \\
    }

void visible_setup(void)
{
    IRQ_CONNECT(3, 1, other_isr, NULL, 0);
}
"""
    parser = Parser(Language(tree_sitter_c.language()))
    tree = parser.parse(src)
    spellings = frozenset(load_thread_patterns(None) and {p.name for p in DEFAULT_SPAWN_PATTERNS})

    hidden = count_macro_body_registrations(tree, src, spellings)
    visible = _sites(src)

    assert hidden == 1, f"the registration inside the #define body must be counted, got {hidden}"
    assert [site[ENTRY] for site in visible] == ["other_isr"], (
        f"only the call outside the macro body is harvested, got {visible}"
    )


def test_two_handlers_of_the_same_name_resolve_to_their_own_file(tmp_path) -> None:
    """MEASURED ON ZEPHYR, AND IT COST THE FEATURE ITS BEST FINDING. `button_pressed` is defined
    in samples/bluetooth/encrypted_advertising/central AND .../peripheral, each registered in its
    own file, each calling k_sleep — a textbook violation. The bare name resolved to two
    candidates, so both threads got a NULL entry, no closure, and no conflict: the layer found
    the handlers and could say nothing about either.

    A handler is normally `static` and registered in the file that defines it, so the file is
    the disambiguator that is always available. Falling back to it is not a guess — it is the
    same identity rule the rest of the pipeline uses when a name is ambiguous, and never merges
    two same-named statics into one.

    @brief An ambiguous handler name resolves within its own file.
    @version 1
    """
    import sqlite3

    from clew.threads import extract_threads

    db = tmp_path / "clew.db"
    (tmp_path / "src").mkdir()
    for index, folder in enumerate(("a", "b"), start=1):
        path = tmp_path / "src" / f"{folder}.c"
        path.write_text(
            "void k_sleep(int t);\n"
            "static void button_pressed(void)\n"
            "{\n"
            "    k_sleep(1);\n"
            "}\n"
            "void setup(void)\n"
            "{\n"
            "    gpio_init_callback(&cb, button_pressed, 1);\n"
            "}\n"
        )
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT,
            file_id INTEGER, bodyfile_id INTEGER, bodystart INTEGER, bodyend INTEGER);
        CREATE TABLE call_edges (
            caller_rowid INTEGER, callee_rowid INTEGER, source TEXT, confidence TEXT);
        INSERT INTO path (rowid, name) VALUES (1, 'src/a.c'), (2, 'src/b.c');
        INSERT INTO memberdef (rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend)
          VALUES (1, 'function', 'button_pressed', 1, 1, 2, 5),
                 (2, 'function', 'setup', 1, 1, 6, 9),
                 (3, 'function', 'button_pressed', 2, 2, 2, 5),
                 (4, 'function', 'setup', 2, 2, 6, 9);
        """
    )
    conn.commit()
    conn.close()

    extract_threads(db, tmp_path)

    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT t.name, t.entry_memberdef_rowid, p.name FROM threads t "
        "LEFT JOIN path p ON p.rowid = t.spawn_path_rowid WHERE t.kind = 'isr' "
        "ORDER BY p.name"
    ).fetchall()
    conn.close()

    assert [(r[1], r[2]) for r in rows] == [(1, "src/a.c"), (3, "src/b.c")], (
        f"each registration must resolve to the handler defined beside it, got {rows}"
    )
