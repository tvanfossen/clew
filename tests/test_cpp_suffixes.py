# SPDX-License-Identifier: MIT
"""Every C++ suffix doxygen indexes is parsed by the AST layers too (R5-CORE C2; 2.0.0).

FOUND BY THE 2.0.0 CORE AUDIT (agent C, vetted, owner-approved): `_ts_language_for` returned None
for `.ipp` and `.inl`, which doxygen's forced default FILE_PATTERNS already indexes — so their
symbols had doxygen rows while every AST layer (calls, locks, threads, blocking, macro refs) saw
no file. Boost (`.ipp`) and Eigen-style header-only libraries (`.inl`) were affected. The same
held for the other C++ suffixes in that list: modules (`.ixx`, `.cppm`, `.cxxm`, `.c++m`) and
preprocessed output (`.ii`, `.i++`).

@brief Tests C++ suffix routing.
@version 1
"""

from __future__ import annotations

import pytest

from clew.doxygen import DOXYGEN_DEFAULT_FILE_PATTERNS
from clew.harvest import _ts_language_for

## doxygen's C++ suffixes — its default list minus C, headers routed elsewhere, and non-C-family.
_CPP_IN_DOXYGEN = (".ipp", ".inl", ".ixx", ".cppm", ".cxxm", ".c++m", ".ii", ".i++")


@pytest.mark.parametrize("suffix", _CPP_IN_DOXYGEN)
def test_a_doxygen_indexed_cpp_suffix_has_a_grammar(suffix: str) -> None:
    """@brief The AST router parses what doxygen indexes, as C++."""
    assert f"*{suffix}" in DOXYGEN_DEFAULT_FILE_PATTERNS, "the premise: doxygen indexes it"
    grammar = _ts_language_for(f"include/detail/impl{suffix}")
    assert grammar is not None
    assert grammar.key == "cpp", grammar.key
