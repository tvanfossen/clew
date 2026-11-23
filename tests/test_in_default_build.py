# SPDX-License-Identifier: MIT
"""A gate says whether the code it guards is compiled in the default build (T5 served; 2.0.0).

FOUND BY THE 2.0.0 UNDERPERFORMANCE REVIEW (mbedtls F1, theme 5): "what is in the default build"
was not answerable. P2 gave every branch its polarity (`form`: an `#else` of `#ifdef X` reads
`ifndef`), and `default_state` already says whether X is on as the repository ships. The reader
still had to combine the two, and the 1.4.0 grid shows that step going wrong: the
MBEDTLS_PLATFORM_MEMORY-on branch of `mbedtls_calloc` was described as the normal path.

`in_default_build` is that combination: true or false where form and default both decide it, and
ABSENT (None) where either does not: an `if_expr` asserts dependence with no polarity, and an
undecided default is not off.

@brief Tests the default-build answer on a gate.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.config_defaults import ensure_config_defaults_table
from clew.query.kconfig import _with_defaults
from clew.query.models import KconfigGate


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    """@brief A config_defaults table: X on, Y off, Z undecided (two disagreeing profiles)."""
    c = sqlite3.connect(tmp_path / "clew.db")
    ensure_config_defaults_table(c)
    c.executemany(
        "INSERT INTO config_defaults (macro, state, file_path, line, origin) VALUES (?, ?, ?, ?, 'heuristic')",
        [
            ("X", "on", "include/config.h", 1),
            ("Y", "off", "include/config.h", 2),
            ("Z", "on", "configs/a.h", 1),
            ("Z", "off", "configs/b.h", 1),
        ],
    )
    return c


def _gate(macro: str, form: str) -> KconfigGate:
    """@brief A gate. @return It."""
    return KconfigGate(symbol=macro, macro=macro, form=form, file_path="src/a.c", line=1)


@pytest.mark.parametrize(
    ("macro", "form", "expected"),
    [
        ("X", "ifdef", True),
        ("X", "ifndef", False),
        ("Y", "ifdef", False),
        ("Y", "ifndef", True),
        ("X", "if_expr", None),
        ("Z", "ifdef", None),
        ("UNKNOWN", "ifdef", None),
    ],
)
def test_form_and_default_decide_it_or_it_is_absent(conn, macro, form, expected) -> None:
    """@brief Both known: decided. Either unknown: None, never False."""
    (gate,) = _with_defaults(conn, (_gate(macro, form),))
    assert gate.in_default_build is expected
