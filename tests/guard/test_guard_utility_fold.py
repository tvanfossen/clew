# SPDX-License-Identifier: MIT
"""`@dg_internal` is gone: it folds into `@utility`, and the old tag is refused by name (PG1; 2.0.0).

OWNER 2026-11-19: "2.0.0 is a good time for a hard cut of doxygen-guard priors — clew only". The
`dg_` prefix is doxygen-guard's. NOT renamed to `@internal`: doxygen's own `\\internal` hides every
tag after it in the block when INTERNAL_DOCS is off (doxygen's default) — the bug the tool-owned
tag was created to avoid, recorded above `EXEMPTION_TAGS` in clew/guard/checks.py. Measured on
entropic: 1,069 of its 1,082 C/C++ blocks carrying the tag have tags after it.

THE REFUSAL CANNOT BE SWITCHED OFF. It is not an unknown-tag warning (`known_tags_warn: false`
silences those): a hard cut that a key can soften is not a hard cut, and a silenced `@dg_internal`
would also stop exempting, so the function would fail `@req` coverage with no word about why.

@brief Tests the `@dg_internal` → `@utility` fold.
@version 1
"""

from __future__ import annotations

from guard_helpers import parse_c

from clew.guard.checks import EXEMPTION_TAGS, check_removed_tags
from clew.guard.config import CONFIG_DEFAULTS, deep_merge


def _func(src: str):
    """@brief Parse one C function. @return The Function."""
    funcs = parse_c(src)
    assert funcs, "the fixture must parse"
    return funcs[0]


_OLD = "/**\n * @brief Helper.\n * @version 1.0\n * @dg_internal\n */\nstatic int helper(void) { return 0; }\n"
_NEW = _OLD.replace("@dg_internal", "@utility")


def test_dg_internal_is_no_longer_an_exemption() -> None:
    """@brief The exemption set is the tool's own: utility and callback."""
    assert "dg_internal" not in EXEMPTION_TAGS
    assert {"utility", "callback"} <= EXEMPTION_TAGS


def test_dg_internal_is_refused_naming_its_replacement() -> None:
    """@brief One violation, pointing at @utility."""
    (v,) = check_removed_tags(_func(_OLD), "a.c", CONFIG_DEFAULTS)
    assert v.check == "tag" and "@dg_internal" in v.message and "@utility" in v.message


def test_the_refusal_survives_known_tags_warn_off() -> None:
    """@brief Not an unknown-tag warning: `known_tags_warn: false` does not silence it."""
    config = deep_merge(CONFIG_DEFAULTS, {"validate": {"known_tags_warn": False}})
    assert len(check_removed_tags(_func(_OLD), "a.c", config)) == 1


def test_utility_is_accepted() -> None:
    """@brief The replacement passes."""
    assert check_removed_tags(_func(_NEW), "a.c", CONFIG_DEFAULTS) == []
