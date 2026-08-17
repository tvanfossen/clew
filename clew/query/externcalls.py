# SPDX-License-Identifier: MIT
"""The callees a function has that the index holds no function for.

`call_edges.callee_rowid` is `NOT NULL REFERENCES memberdef(rowid)`, so a call
whose callee cannot be resolved to an indexed function is not merely low
confidence — it is UNREPRESENTABLE. The name is discarded at fold time and the
graph is silent about it.

That silence is measurable. On mbedtls all four `threading_mutex_*_pthread`
wrappers report an EMPTY `callees` list, because the only thing each one calls is
a pthread primitive that lives in libc and is not indexed. The wrapper's entire
purpose is invisible in the graph, and the only way to learn it was to read the
body — which is exactly what a graded question forced four times.

So this module recovers the NAMES, at query time, from the same tree-sitter walk
the build uses, and hands them back as `ExternalCallee` rows. Three deliberate
limits on the claim:

  * NOT an edge. Nothing is inserted, nothing is synthesized. A resolved
    `call_edges` row is traversed by `mark_reachability` and the thread BFS; a
    row asserting a reachable name that resolves to nothing would inherit the
    weakest link and propagate as fact.
  * NOT merged into `callees`. Those rows are resolved by contract, and a
    consumer that trusts the contract must not have to re-check it.
  * CONSERVATIVE about "external": a harvested name is reported only when NO
    `memberdef` row of ANY kind carries it. A name that is indexed but whose edge
    is missing for some other reason is not this module's claim to make.

TWO FILTERS, BOTH ADDED AFTER MEASURING THE UNFILTERED PANEL, because the first
version was noise on Python:

  * **Bare identifiers only** (`ast`, not `ast_member`). A member/qualified call
    is recovered by unwrapping `obj.execute()` or `Ns::f()` down to its
    unqualified TAIL, and resolving that tail needs the receiver's declared type —
    79% of member-ish sites, and a much larger job. So an unresolved tail says
    almost nothing: measured on this repo's own index, `_shrink_to_budget`
    reported `get`, `items` and `dumps` as things it "calls out of the index",
    which is true of the token and useless as a fact. `pthread_mutex_lock(&m)`
    is a BARE identifier, which is why the case this exists for survives the
    filter. The cost is real and bounded: a C++ call to an unindexed
    `Ns::helper()` is not reported.
  * **Python builtins are dropped, in Python files only.** `len`, `str`, `max`
    and `isinstance` are unindexed and technically external, and eight of them
    crowded out the one interesting row. The list is read from the `builtins`
    MODULE rather than written here — a language fact, not a repo convention —
    and it is applied only when the file's grammar is Python, because `abs`,
    `pow` and `open` are also real libc functions and a C file calling them
    means it.

Degrades to `[]` — never raises — when tree-sitter or its grammars are absent,
when the working tree cannot be read, or when the file's extension has no
grammar. That is the same graceful-fallback contract the build's AST layers
carry, for the same reason: an index built without tree-sitter must still answer.

@brief Query-time recovery of unresolvable callee names from a function body.
@version 1
"""

from __future__ import annotations

import builtins
import sqlite3
from pathlib import Path
from typing import Any

from ..call_edges import _ast_harvest_calls
from ..harvest import _ast_parse_one_file, _ts_language_for, try_import_tree_sitter
from ..vocabulary import CALL_SOURCE_AST
from .models import ExternalCallee

## Read from the interpreter, never written out. A literal list would rot against the
## Python version the target repo is written in, and would be the one hardcoded language
## assumption in a module whose whole job is to report what the index could not name.
_PY_BUILTINS = frozenset(dir(builtins))

## How many DISTINCT unresolvable names one dossier reports. A function that calls
## thirty platform primitives has told the reader what it is well before the thirtieth,
## and the one-shot exists to cut cost, not to move it.
MAX_EXTERNAL_CALLEES = 24
## Call sites listed per name. `memcpy` called eleven times needs one line number to be
## findable and does not need eleven.
MAX_LINES_PER_CALLEE = 6


## @brief Harvest every call site inside one file, or None when it cannot be parsed.
## @param repo_root Working-tree root the recorded path is relative to.
## @param file Repo-relative source path as the index recorded it.
## @return List of `[callee_name, line, source, qualifier]` sites, or None on any failure.
## @version 1
## @dg_internal
def _harvest_file(repo_root: Path, file: str) -> list[list[Any]] | None:
    """Parses the WHOLE FILE rather than the body slice, which costs more and is the
    right trade. A body slice is not a valid translation unit: an out-of-line C++
    member definition parses on its own, but a Python METHOD body is indented and the
    Python grammar rejects it, and a C body containing an unbalanced `#if` recovers
    differently in isolation than in place. Parsing the file and range-filtering the
    result asks the grammar only questions it can answer.

    The path is resolved and containment-checked exactly as `source._read_body` does —
    a foreign or tampered index could record an absolute or `../`-escaping body path,
    and this reader must refuse it for the same reason that one does.

    @brief Parse one indexed file and harvest its call sites.
    @return Harvested sites, or None.
    @version 1
    """
    imported = try_import_tree_sitter()
    if imported is None:
        return None
    language, parser = imported
    root = repo_root.expanduser().resolve()
    abs_path = (root / file).resolve()
    if not abs_path.is_relative_to(root):
        return None
    parsed = _ast_parse_one_file(file, abs_path, {}, parser, language)
    if parsed is None:
        return None
    tree, src_bytes = parsed
    try:
        return _ast_harvest_calls(tree, src_bytes)
    except (AttributeError, ValueError, UnicodeDecodeError):
        return None


## @brief Group harvested call sites by callee name, in source order.
## @param sites Harvested `[name, line, ...]` sites already filtered to one body.
## @return Ordered mapping of callee name to its ascending call lines.
## @version 2
## @dg_internal
def _by_name(sites: list[list[Any]]) -> dict[str, list[int]]:
    """SORTED BY LINE FIRST, because the harvester walks the tree with a STACK and
    therefore emits a body's call sites in roughly reverse source order — the first
    unfiltered output reported `pthread_mutex_lock` at `[208, 207, 205, 202, 198, 192]`,
    descending, which reads as corrupt and makes the cap keep the LAST few call sites
    instead of the first.

    Grouping then preserves that source order, so the first thing a function calls leads
    the panel and the cap drops the tail rather than the head.

    @brief Group call sites by name in ascending line order.
    @version 2
    """
    grouped: dict[str, list[int]] = {}
    for site in sorted(sites, key=lambda s: int(s[1])):
        name, line = str(site[0]), int(site[1])
        lines = grouped.setdefault(name, [])
        if len(lines) < MAX_LINES_PER_CALLEE and line not in lines:
            lines.append(line)
    return grouped


## @brief The sites eligible to be reported, after the two noise filters.
## @param sites Harvested sites already range-filtered to one body.
## @param is_python True when the enclosing file's grammar is Python.
## @return The subset worth naming.
## @version 1
## @dg_internal
def _reportable(sites: list[list[Any]], is_python: bool) -> list[list[Any]]:
    """See the module docstring for why each filter exists and what each costs. Both are
    applied HERE rather than at the grouping step so that a reader can see the whole
    narrowing in one place — the panel's honesty depends on knowing exactly what it does
    not say.

    A site cached by an older extraction may be two elements long, with no provenance
    tag; `_ast_harvest_calls` tolerates that shape and so does this, treating an
    untagged site as the bare-identifier case it used to be.

    @brief Drop member-tail sites, and Python builtins in Python files.
    @return Reportable sites.
    @version 1
    """
    bare = [s for s in sites if (s[2] if len(s) > 2 else CALL_SOURCE_AST) == CALL_SOURCE_AST]
    return [s for s in bare if str(s[0]) not in _PY_BUILTINS] if is_python else bare


## @brief True when the index holds no memberdef of any kind under this name.
## @param conn Open connection to the index.
## @param name A harvested callee name.
## @return True when the name is unknown to the index.
## @version 1
## @dg_internal
def _unindexed(conn: sqlite3.Connection, name: str) -> bool:
    """ANY kind, not just `function`. A macro is a `define` memberdef and the macro-hop
    layer already reaches through it; a name matching an indexed macro is therefore
    something the graph can speak about, and claiming it as external would be a
    fabricated gap.

    @brief Report whether a name is absent from `memberdef` entirely.
    @version 1
    """
    return conn.execute("SELECT 1 FROM memberdef WHERE name=? LIMIT 1", (name,)).fetchone() is None


## @brief The unresolvable callee names a function's own body calls.
## @param conn Open connection to the index.
## @param repo_root Working-tree root the recorded body path is relative to.
## @param file Repo-relative body file as the index recorded it.
## @param start First line of the body extent (inclusive).
## @param end Last line of the body extent (inclusive).
## @return ExternalCallee rows in source order, capped; empty when nothing is unresolvable.
## @version 1
## @req REQ-DDB-QUERY-001
def external_callees(
    conn: sqlite3.Connection,
    repo_root: Path | str,
    file: str,
    start: int,
    end: int,
) -> list[ExternalCallee]:
    """Answer "this function calls out of the index, to these names" for the body
    extent `file:start..end`.

    The extent comes from the resolved identity's own `memberdef` row, so the caller
    has already decided WHICH same-named function is being described (gh#26) and this
    cannot attribute one identity's calls to another. Sites are filtered by line, which
    includes calls inside lambdas and nested blocks — correctly: those are calls this
    function's text makes.

    An empty list means one of two things and does not distinguish them: every callee
    resolved, or the body could not be parsed. That is acceptable here and only here,
    because the field is ADDITIVE — a consumer that gets nothing is exactly as informed
    as it was before this existed — and because the alternative, an "unknown" sentinel
    in a one-shot payload, spends bytes on every function to describe a condition the
    payload cannot act on.

    @brief List a function body's unresolvable callee names.
    @return Capped ExternalCallee rows, in source order.
    @version 2
    """
    sites = _harvest_file(Path(repo_root), file)
    if not sites:
        return []
    within = [s for s in sites if start <= int(s[1]) <= end]
    lang = _ts_language_for(file)
    reportable = _reportable(within, is_python=lang is not None and "python" in lang.__name__)
    found: list[ExternalCallee] = []
    for name, lines in _by_name(reportable).items():
        if len(found) >= MAX_EXTERNAL_CALLEES:
            break
        if _unindexed(conn, name):
            found.append(ExternalCallee(name=name, call_lines=tuple(lines)))
    return found
