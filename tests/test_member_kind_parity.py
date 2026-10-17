# SPDX-License-Identifier: MIT
"""The write side's doxygen kind strings and the read side's must be the same strings.

1.1.0. `clew/synth.py` writes a CMake `macro` as a `memberdef` row whose `kind` is
doxygen's own "macro definition", so that `clew/query/macros.py` — which selects exactly
that string — finds it and reports it as a macro rather than as a function.

WHY A TEST AND NOT AN IMPORT. `clew/query/macros.py` says of its constant: *"Spelled once:
it is a doxygen vocabulary string, not ours, and a second literal copy is the drift that
silently empties one caller while the other keeps working."* That is right, and the second
copy now exists — because the alternative is worse. `clew/synth.py` is pipeline code and
`clew/query/*` is the read side; importing the query layer from the pipeline inverts the
layering the package is built on, for one string.

So the copy is deliberate and this test is what makes it safe: a rename on either side
fails here, which is precisely the drift the original comment warns about.

@brief The two spellings of doxygen's macro kind agree.
@version 1
"""

from __future__ import annotations

from clew.query.macros import MACRO_KIND
from clew.synth import MEMBER_KIND


def test_the_macro_kind_the_front_end_writes_is_the_one_the_query_selects() -> None:
    """@brief The written kind equals the selected kind. @version 1"""
    assert MEMBER_KIND["macro"] == MACRO_KIND


def test_a_function_is_written_as_doxygens_function_kind() -> None:
    """`kind='function'` is what every function-shaped query in the read side filters on,
    so a front end writing anything else would produce rows no caller can see.

    @brief The function kind is doxygen's own. @version 1
    """
    assert MEMBER_KIND["function"] == "function"


def test_every_kind_a_walker_can_emit_has_a_mapping() -> None:
    """The walkers' own vocabulary, gathered from them rather than restated here: a new
    kind added to a walker with no entry in the map raises KeyError at write time, on a
    build, for one file type. This fails in CI instead.

    @brief Every walker kind maps to a doxygen kind. @version 1
    """
    from clew.cmakeast import _DEFINITIONS

    emitted = {kind for _command, kind in _DEFINITIONS.values()}
    ## Shell emits no `kind` at all and falls back to "function" — pinned here so that a
    ## walker that starts emitting one does not land on a missing mapping.
    emitted.add("function")

    assert emitted <= set(MEMBER_KIND), f"unmapped walker kinds: {emitted - set(MEMBER_KIND)}"
