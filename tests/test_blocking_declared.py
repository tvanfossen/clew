# SPDX-License-Identifier: MIT
"""A repository declares its own blocking primitives, ISR predicates and wait tokens (R5-CORE C1; 2.0.0).

FOUND BY THE 2.0.0 CORE AUDIT (agent C, vetted, owner-approved): every sibling layer (`locks`,
`thread_patterns`, `shared_key_patterns`) was declarable and this one was the exception — the
primitive set was closed at Zephyr, FreeRTOS, RIOT and POSIX, so a repository's own
`os_sem_wait(sem, ms)` was invisible and NuttX's `up_interrupt_context()` was not a guard. A
declared `blocking:` section ADDS to the built-ins, which are facts about those RTOSes.

@brief Tests the blocking declaration.
@version 1
"""

from __future__ import annotations

import pytest

from clew.tsnode import Parser


def _sites(source: str, declared: dict | None = None) -> list[list]:
    """@brief Blocking sites one C source yields under a declaration. @return Site records."""
    from clew.blocking import blocking_harvester

    tree = Parser("c").parse(source.encode())
    return blocking_harvester(declared).harvest(tree, source.encode())


_DECLARED = {
    "primitives": [{"name": "os_sem_wait", "timeout_arg_index": 1}],
    "isr_predicates": ["up_interrupt_context"],
    "wait_tokens": {
        "forever": ["OS_WAIT_FOREVER"],
        "none": ["OS_NO_WAIT"],
        "bounded_prefixes": ["OS_MS"],
    },
}


def test_a_declared_primitive_and_its_wait_tokens_are_read() -> None:
    """@brief `os_sem_wait(s, OS_WAIT_FOREVER)` is a forever wait; `OS_MS(5)` a bounded one."""
    src = "void f(void) { os_sem_wait(&s, OS_WAIT_FOREVER); os_sem_wait(&s, OS_MS(5)); os_sem_wait(&s, OS_NO_WAIT); }"
    waits = [s[2] for s in sorted(_sites(src, _DECLARED), key=lambda s: s[3])]
    assert sorted(waits) == ["bounded", "forever", "none"], waits
    assert _sites(src) == [], "undeclared, the primitive is not known"


def test_a_declared_isr_predicate_guards() -> None:
    """@brief A call of a declared predicate in the enclosing condition is a guard."""
    src = "void f(void) { if (!up_interrupt_context()) { os_sem_wait(&s, OS_WAIT_FOREVER); } }"
    (site,) = _sites(src, _DECLARED)
    assert "up_interrupt_context" in site[4]


def test_the_built_ins_still_apply_beside_a_declaration() -> None:
    """@brief Declaring adds: `k_sem_take(&s, K_FOREVER)` is still found and still forever."""
    (site,) = _sites("void f(void) { k_sem_take(&s, K_FOREVER); }", _DECLARED)
    assert (site[0], site[2]) == ("k_sem_take", "forever")


@pytest.mark.parametrize(
    "bad",
    [
        {"primitive": [{"name": "x"}]},
        {"primitives": [{"name": "x", "timeout_arg": 1}]},
        {"primitives": [{"timeout_arg_index": 1}]},
        {"wait_tokens": {"forevr": ["X"]}},
        {"isr_predicates": "up_interrupt_context"},
    ],
)
def test_a_malformed_declaration_is_refused_by_name(bad: dict) -> None:
    """@brief Unknown keys, a missing name and a wrong shape are refused, never defaulted."""
    from clew.blocking import blocking_harvester
    from clew.vocabulary import DeclarationError

    with pytest.raises(DeclarationError):
        blocking_harvester(bad)


def test_the_declaration_changes_the_cache_key() -> None:
    """A cached payload from the built-in vocabulary must not be served for a declared one.

    @brief The declaration is in the harvester's key.
    """
    from clew.blocking import blocking_harvester

    assert blocking_harvester(_DECLARED).extra_key != blocking_harvester(None).extra_key


def test_the_section_keys_match_the_reader() -> None:
    """@brief declaration.SECTION_KEYS['blocking'] is the reader's own key set."""
    from clew.blocking import BLOCKING_KEYS
    from clew.declaration import SECTION_KEYS

    assert SECTION_KEYS["blocking"] == BLOCKING_KEYS
