# SPDX-License-Identifier: MIT
"""Doxygen's own commands are known tags; a typo of an enforced tag is still caught (PG7; 2.0.0).

FOUND BY A CONSUMER (the entropic session, on PG2's first run over its headers): `@p` (11, with
the hint "did you mean @pre?"), `@code` ("did you mean @todo?"), `@endcode` and `@c` were reported
as unknown tags. They are built-in doxygen commands; the gate's known set listed about 25 of
doxygen's ~200 commands, missing the inline formatting ones that API documentation in headers
uses most, and the hint sent the reader the wrong way.

THE GATE RECOGNISES DOXYGEN'S WHOLE BUILT-IN VOCABULARY and still enforces only its structural
tags (@brief, @version, @return, @req ...). An unknown-tag check exists to catch typos and
undeclared project tags, and a doxygen command is neither.

@brief Tests the gate's doxygen vocabulary.
@version 1
"""

from __future__ import annotations

import pytest

from clew.guard.checks import check_unknown_tags
from clew.guard.config import CONFIG_DEFAULTS
from clew.guard.parser import DoxygenBlock, Function


def _func(*tags: str) -> Function:
    """@brief A function whose block carries these tags. @return Function."""
    block = DoxygenBlock(
        start_line=0,
        end_line=3,
        tags={"brief": ["B."], "version": ["1.0"], **{t: [""] for t in tags}},
    )
    return Function(name="f", def_line=4, body_end=6, doxygen=block)


@pytest.mark.parametrize(
    "tag",
    [
        "p",
        "c",
        "a",
        "e",
        "b",
        "em",
        "code",
        "endcode",
        "verbatim",
        "endverbatim",
        "retval",
        "sa",
        "ref",
        "link",
        "endlink",
        "attention",
        "remark",
        "remarks",
        "bug",
        "tparam",
        "ingroup",
        "n",
    ],
)
def test_a_doxygen_command_is_a_known_tag(tag: str) -> None:
    """@brief No unknown-tag finding for a built-in doxygen command."""
    assert check_unknown_tags(_func(tag), "a.h", CONFIG_DEFAULTS) == []


def test_a_typo_of_an_enforced_tag_is_still_caught() -> None:
    """@brief `@versoin` is no doxygen command: flagged, pointing at @version."""
    (v,) = check_unknown_tags(_func("versoin"), "a.h", CONFIG_DEFAULTS)
    assert "@versoin" in v.message and "@version" in v.message
