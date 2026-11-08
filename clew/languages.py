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


## The columns of the published support table: (capability key, column heading).
##
## THREE, AND EACH ONE IS MEASURED. `tests/test_language_capabilities.py` builds a two-function
## fixture per language and asserts these cells equal what the build produced, in both directions.
## CONCURRENCY IS DELIBERATELY ABSENT: measured, it varies by PATTERN within a language — a C++
## named-local `std::thread` was not seen where other C++ spawn forms are — so a yes/no cell would
## be wrong whichever way it was set. The per-language docs carry it instead.
SUPPORT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("symbols", "Symbols"),
    ("calls", "Call graph"),
    ("docs", "Doc comments"),
)

_ALL = frozenset(key for key, _ in SUPPORT_COLUMNS)

## What each harvested language yields. A DECLARATION, because capability is not readable off a
## router table — but a declaration a test re-measures on every run, so it cannot drift the way
## the old prose did. SHELL AND CMAKE ARE THE REASON THIS EXISTS: their functions are named and
## documented, but a call between them is not graphed, and the flat "harvests symbols from ..."
## line put them beside C as if "who calls this" worked for both.
_DECLARED: dict[str, frozenset[str]] = {
    "C": _ALL,
    "C++": _ALL,
    "Rust": _ALL,
    "Python": _ALL,
    "JavaScript": _ALL,
    "TypeScript": _ALL,
    "shell": frozenset({"symbols", "docs"}),
    "CMake": frozenset({"symbols", "docs"}),
}

## Restricted to what the routers actually harvest, so a front end removed from a router drops
## out of the table rather than leaving its row behind.
CAPABILITIES: dict[str, frozenset[str]] = {
    name: _DECLARED[name] for name in HARVESTED if name in _DECLARED
}

## Where the table's links point. ABSOLUTE, because the README is also the PyPI description and a
## relative link 404s there — `tests/test_doc_links.py` records the README's links "had to become
## absolute so PyPI renders them". `main`, not a tag: the docs a reader wants are the current ones.
REPO_URL = "https://github.com/tvanfossen/clew/blob/main/"

## The per-language page each table row links to, repo-relative. A test asserts every target
## exists, so the table cannot ship a dead link.
DOC_PAGE: dict[str, str] = {
    "C": "docs/languages/C_INTEGRATION.md",
    "C++": "docs/languages/CPP_INTEGRATION.md",
    "Rust": "docs/languages/RUST_INTEGRATION.md",
    "Python": "docs/languages/PYTHON_INTEGRATION.md",
    "JavaScript": "docs/languages/JS_TS_INTEGRATION.md",
    "TypeScript": "docs/languages/JS_TS_INTEGRATION.md",
    "shell": "docs/languages/SCRIPT_INTEGRATION.md",
    "CMake": "docs/languages/SCRIPT_INTEGRATION.md",
}


## @brief The language support table, as markdown.
## @return One row per harvested language plus one for the registered-only types.
## @version 1
## @utility
def support_table() -> str:
    """GENERATED, NEVER HAND-EDITED — `scripts/sync_metadata.py` writes it between markers and its
    `--check` hook fails a commit that lets it drift. Each language links to its integration page,
    so the table is also the README's index into the per-language detail.

    REGISTERED-ONLY TYPES GET ONE ROW, honestly labelled: they are in the file set and findable by
    name, and contribute no symbols — `dossier` on a Perl subroutine has nothing to return.

    @brief Render the support table.
    @return Markdown table text.
    @version 1
    """
    head = "| Language | " + " | ".join(title for _, title in SUPPORT_COLUMNS) + " |"
    rule = "|---|" + "|".join(":-:" for _ in SUPPORT_COLUMNS) + "|"
    rows = [head, rule]
    for name, caps in CAPABILITIES.items():
        cells = " | ".join("✓" if key in caps else "—" for key, _ in SUPPORT_COLUMNS)
        rows.append(f"| [{name}]({REPO_URL}{DOC_PAGE[name]}) | {cells} |")
    if REGISTERED_ONLY:
        rest = " | ".join("—" for _ in SUPPORT_COLUMNS[1:])
        rows.append(f"| {', '.join(REGISTERED_ONLY)} | name only | {rest} |")
    return "\n".join(rows)


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
