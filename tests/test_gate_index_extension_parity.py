# SPDX-License-Identifier: MIT
"""WHAT THE INDEX READS, THE GATE MUST BE ABLE TO CHECK.

Group A, 1.1.0 merge review. clew carries four hardcoded extension tables for the INDEX
(`harvest._CPP_EXTS`, `harvest._PY_EXTS`, `harvest._TS_EXTS`, `synth.SYNTH_EXTS`) and a fifth
for the GATE (`guard.config`'s per-language `extensions`). They drifted: seven extensions were
indexed and ungateable, so a `.hh` header or a `.mts` module got symbols, call edges and
requirement links in the graph while `clew guard` skipped it with a DEBUG line nobody sees.

An owner whose C++ headers or TypeScript modules are silently unchecked is the worst failure
mode this tool has, because the gate's whole value is the claim that what it passed is
documented.

WHY THIS IS A PARITY TEST AND NOT A COLLAPSE ONTO ONE TABLE. The merge review asked for the
five lists to be derived from `lang_parsing_substrate.languages()`. Measured, that registry is
NARROWER than clew's own tables — it lists no `.h`, `.hh`, `.h++`, `.c++`, `.mts`, `.cts` or
`.pyi` — so deriving from it would DROP `.h` from the gate's C configuration, which for a C
project is every header it has. The substrate decides which GRAMMAR parses a file; which
extensions clew claims is clew's own statement, and this test is what keeps the two statements
clew makes about it in agreement.

@brief The gate's extension tables cover everything the index claims.
@version 1
"""

from __future__ import annotations

import pytest

from clew.guard.config import OPT_IN_LANGUAGE_DEFAULTS, VALIDATE_DEFAULTS
from clew.harvest import _CPP_EXTS, _PY_EXTS, _TS_EXTS
from clew.synth import SYNTH_EXTS

## Every extension the INDEX claims, with the table that claims it — so a failure names the
## list to change rather than only the extension. `.c`, `.h` and `.rs` are claimed through
## doxygen and rustdoc rather than through a harvest table, and are stated here for the same
## reason: this test's subject is what the index reads, not where the string happens to live.
_INDEX_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "harvest._CPP_EXTS": _CPP_EXTS,
    "harvest._PY_EXTS": _PY_EXTS,
    "harvest._TS_EXTS": _TS_EXTS,
    "synth.SYNTH_EXTS": SYNTH_EXTS,
    "doxygen (C)": (".c", ".h"),
    "rustdoc": (".rs",),
}


## @brief Every extension any gate language configuration claims.
## @return The set of extensions, lowercased.
## @version 1
def _gate_extensions() -> set[str]:
    """@brief Collect the gate's claimed extensions. @return The set."""
    configs = list(VALIDATE_DEFAULTS["languages"].values()) + list(
        OPT_IN_LANGUAGE_DEFAULTS.values()
    )
    return {ext.lower() for config in configs for ext in config.get("extensions", [])}


@pytest.mark.parametrize("table", sorted(_INDEX_EXTENSIONS))
def test_every_indexed_extension_is_gateable(table: str) -> None:
    """@brief Each index table's extensions are all claimed by some gate language. @version 1"""
    gate = _gate_extensions()
    ungateable = sorted(ext for ext in _INDEX_EXTENSIONS[table] if ext.lower() not in gate)

    assert not ungateable, (
        f"{table} is indexed but the gate claims no language for {ungateable}, so these files "
        f"get symbols, call edges and requirement links in the graph while `clew guard` skips "
        f"them silently"
    )


def test_the_gate_claims_no_extension_the_index_cannot_read() -> None:
    """THE OTHER DIRECTION, which is a different failure: the gate demanding documentation in a
    file the index will never hold is a rule with no graph behind it, and the owner has no way
    to see why. Asserted so the two tables cannot drift apart in either direction.

    @brief Every gate extension is one the index claims. @version 1
    """
    indexed = {ext.lower() for exts in _INDEX_EXTENSIONS.values() for ext in exts}
    orphaned = sorted(_gate_extensions() - indexed)

    assert not orphaned, (
        f"the gate claims {orphaned}, which no index front end reads — either add it to the "
        f"index's tables or drop it from the gate's"
    )
