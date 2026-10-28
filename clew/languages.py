# SPDX-License-Identifier: MIT
"""WHAT CLEW INDEXES, DERIVED FROM THE ROUTERS RATHER THAN WRITTEN DOWN.

**THE LANGUAGE LIST WAS PROSE IN FIVE PLACES AND A CRAWLER FOUND IT BEFORE THE GATE DID.** clew
grew JavaScript, TypeScript, shell and CMake front ends; two of the five public strings naming
its languages were updated and three were not, including the MCP `INSTRUCTIONS` block — the first
thing every agent reads, telling them clew could not index four of the languages it indexes.

**"SIX" WOULD HAVE BEEN WRONG TOO.** `docs/languages/` holds six files, so six is the number a
reader counts, but `SCRIPT_INTEGRATION.md` is one file covering TWO languages clew harvests
symbols from. A hand-maintained list was wrong in both directions at once, which is the argument
for not maintaining one.

**TWO SETS, BECAUSE CLEW DOES TWO DIFFERENT THINGS.** A HARVESTED language contributes symbols,
bodies and call edges to the namespace. A REGISTERED-ONLY type is in the file set and findable by
name and contributes nothing — YAML and JSON by design, `.pl`/`.pm`/`.mk`/`Makefile` because no
grammar reads them. Collapsing them is how "clew supports Perl" becomes a claim it cannot meet:
`dossier` on a Perl subroutine has nothing to return.

**THE EXTENSION TABLES ARE THE SOURCE OF TRUTH, NOT THIS FILE.** Each entry below names the table
it is derived from, so a front end added to a router without a line here produces a language set
that no longer matches the routers — and `test_language_claim_is_derived` fails rather than a
registry serving a stale description. The four static files (pyproject, both plugin manifests,
README) cannot interpolate, so that test checks them against this instead.

DELIBERATELY NOT DERIVED FROM `lang_parsing_substrate.languages()`. That registry is NARROWER
than clew's own tables — it lists no `.h`, `.hh`, `.pyi` — and it carries ten grammars clew
compiles and does not route. What the substrate CAN parse and what clew DOES read are different
facts, and this is the second.
"""

from __future__ import annotations

from .harvest import _CPP_EXTS, _PY_EXTS, _TS_EXTS
from .synth import DATA_EXTS, SCRIPT_EXTS, SCRIPT_NAMES, SYNTH_EXTS, UNPARSED_EXTS, UNPARSED_NAMES

## Each language clew harvests SYMBOLS from, with the router that decides it. The display name is
## the key because it is what reaches a reader; the probe is a callable over the routing tables so
## a table emptied or renamed drops its language rather than leaving the name behind.
##
## `C` IS NOT IN `_CPP_EXTS`. doxygen reads `.c` and `.h` through its own configuration rather
## than through a clew table — `tests/test_gate_index_extension_parity.py` states the same
## exception for the same reason — so it is asserted against the suffixes doxygen is given.
_HARVESTED_PROBES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("C", (".c", ".h")),
    ("C++", _CPP_EXTS),
    ("Rust", (".rs",)),
    ("Python", _PY_EXTS),
    ("JavaScript", tuple(e for e in SYNTH_EXTS if e in (".js", ".mjs", ".cjs", ".jsx"))),
    ## `.tsx` LIVES IN `SYNTH_EXTS` AND NOT IN `_TS_EXTS`, which the completeness check caught on
    ## its first run — the harvest table holds `.ts/.mts/.cts` and the parse front end adds the
    ## JSX-bearing variant. Claiming only `_TS_EXTS` left `.tsx` accounted for by nothing.
    ("TypeScript", _TS_EXTS + tuple(e for e in SYNTH_EXTS if e == ".tsx")),
    ("shell", tuple(e for e in SCRIPT_EXTS if e in (".sh", ".bash"))),
    ("CMake", tuple(e for e in SCRIPT_EXTS if e == ".cmake") + SCRIPT_NAMES),
)

## Types REGISTERED in the file set and harvested by nothing. Named separately from the harvested
## set for the reason this module's docstring gives: they promise a NAME, never a symbol.
_REGISTERED_PROBES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("YAML", tuple(e for e in DATA_EXTS if e in (".yaml", ".yml"))),
    ("JSON", tuple(e for e in DATA_EXTS if e == ".json")),
    ("Perl", tuple(e for e in UNPARSED_EXTS if e in (".pl", ".pm"))),
    ("Make", tuple(e for e in UNPARSED_EXTS if e == ".mk") + UNPARSED_NAMES),
)

## The languages clew harvests symbols from, in the order a reader should meet them: the doxygen
## family first because it is the common case, the parse-built front ends after.
HARVESTED: tuple[str, ...] = tuple(name for name, exts in _HARVESTED_PROBES if exts)

## The types clew registers by name and never harvests.
REGISTERED_ONLY: tuple[str, ...] = tuple(name for name, exts in _REGISTERED_PROBES if exts)


## @brief The harvested languages as one human-readable clause.
## @return e.g. "C, C++, Rust, Python, JavaScript, TypeScript, shell and CMake".
## @version 1
## @utility
def harvested_phrase() -> str:
    """AN OXFORD-FREE `and` BEFORE THE LAST ITEM, because this lands mid-sentence in the served
    MCP instructions and in a PyPI description, where a trailing comma reads as truncation.

    @brief Join the harvested language names.
    @return The clause.
    @version 1
    """
    if len(HARVESTED) < 2:
        return "".join(HARVESTED)
    return f"{', '.join(HARVESTED[:-1])} and {HARVESTED[-1]}"


## @brief The registered-but-unharvested types as one human-readable clause.
## @return e.g. "YAML, JSON, Perl and Make".
## @version 1
## @utility
def registered_phrase() -> str:
    """@brief Join the registered-only type names.
    @return The clause.
    @version 1
    """
    if len(REGISTERED_ONLY) < 2:
        return "".join(REGISTERED_ONLY)
    return f"{', '.join(REGISTERED_ONLY[:-1])} and {REGISTERED_ONLY[-1]}"


## Every extension and whole-name any router claims, with the table that claims it. THE
## COMPLETENESS CHECK READS THIS, not the probe lists — so an extension added to a router and not
## to a probe is DETECTED rather than silently dropped.
##
## THIS IS THE THIRD ATTEMPT AT THIS FIX AND THE FIRST ONE WITH NO MAINTAINED LIST IN IT. Attempt
## one wrote the correct sentence into five files by hand. Attempt two generated the sentence from
## the probes below — and the probes themselves filter to named extensions, so adding `.rb` to
## `UNPARSED_EXTS` changed nothing and the check passed. A derivation with an allow-list inside it
## only ever sees the languages someone already remembered.
_ROUTER_TABLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("harvest._CPP_EXTS", _CPP_EXTS),
    ("harvest._PY_EXTS", _PY_EXTS),
    ("harvest._TS_EXTS", _TS_EXTS),
    ("synth.SYNTH_EXTS", SYNTH_EXTS),
    ("synth.SCRIPT_EXTS", SCRIPT_EXTS),
    ("synth.SCRIPT_NAMES", SCRIPT_NAMES),
    ("synth.DATA_EXTS", DATA_EXTS),
    ("synth.UNPARSED_EXTS", UNPARSED_EXTS),
    ("synth.UNPARSED_NAMES", UNPARSED_NAMES),
    ## doxygen's own C suffixes and rustdoc's, which no clew table holds — stated here for the
    ## reason `test_gate_index_extension_parity` states them: the subject is what the index
    ## READS, not where the string happens to live.
    ("doxygen (C)", (".c", ".h")),
    ("rustdoc", (".rs",)),
)


##
# @brief Extensions a router claims that no language probe accounts for.
# @return Mapping of table name to its unclaimed entries; empty when the map is complete.
# @version 1
# @utility
def unclaimed_extensions() -> dict[str, tuple[str, ...]]:
    """THE ONLY PART THAT MAKES THIS UNABLE TO GO STALE. Everything above derives a SENTENCE from
    a map; this checks the MAP against the routers. Without it, adding a front end leaves the
    sentence correct about the languages it already knew and silent about the new one — which is
    indistinguishable from being up to date.

    Verified by deliberately adding `.rb` to `synth.UNPARSED_EXTS`: the generated clause did not
    move and `sync_metadata.py --check` returned 0. That is the hole this closes.

    @brief Report router entries no probe claims.
    @return Table name -> unclaimed entries.
    @version 1
    """
    claimed = {entry for _name, exts in (*_HARVESTED_PROBES, *_REGISTERED_PROBES) for entry in exts}
    missed: dict[str, tuple[str, ...]] = {}
    for table, entries in _ROUTER_TABLES:
        gap = tuple(e for e in entries if e not in claimed)
        if gap:
            missed[table] = gap
    return missed
