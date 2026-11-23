# SPDX-License-Identifier: MIT
"""The fast refresh tier: an edited file's own layers updated in place, the rest disclosed stale.

1.3.5, Track 2 (two-tier refresh; owner, 2026-11-13). A one-file save cost a whole-index rebuild —
5.6 to 13.8 s on the measured repositories after 1.3.4 — because every stage rebuilds its table
over the whole index. An editor saving a file needs that file's symbols where they now are, now;
the whole-index derivations (reachability, threads, call resolution across files) can follow.

WHAT THE FAST TIER DOES, for each edited file, inside ONE transaction on the live index:
  * SHIFTS the file's symbol positions (`memberdef` line and body span, `compounddef` line, the
    declaration extents) by a line map built from the parser's OWN before/after anchors — the
    file's cached payload for its previous content against a fresh parse of the new one. Both
    sides come from the same harvester, so they measure lines the same way; doxygen's rows move
    by the same delta as the parser's.
  * RECOMPUTES the file's text layers: file-level docs, requirement mentions, generated-file
    evidence.
  * RECORDS `fast.*` in `build_meta` — the files and the layers it did NOT bring current — which
    the `derived` staleness axis serves on every reply until a full build replaces the database.

WHAT IT RECONCILES (PR1, 2.0.0): an added, removed or renamed FUNCTION. A removed one is deleted
with every row referencing it; an added one is written by the full build's own writer with a
provisional rowid, named in `fast.provisional`, its outgoing edges computed now and its inbound
edges left to the full build. See `clew.fasttier_defs`.

WHAT IT REFUSES — each refusal is a full build, never a guess:
  * any OTHER changed definition (a class, a variable, a macro), reshuffled overloads, or a
    removed function that is a thread's entry point;
  * a file in a language with no anchor harvester, or no cached payload for its old content;
  * a configuration input (`.clew.yaml`, a Doxyfile, the requirements catalog, Kconfig, ...);
  * more than `FAST_MAX_FILES` edited files, none at all, or an index from another build version.

THE CACHE'S `source_files` IS NOT ADVANCED. The fast tier writes payloads (keyed by content, so
always safe) but never commits the cache, so the full build that follows still sees every edit
as an edit.

@brief Fast in-place refresh of edited files, with whole-index staleness disclosed.
@version 1
"""

from __future__ import annotations

import bisect
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from ._common import logger
from .buildlock import build_lock
from .fasttier_defs import (
    MEMBERDEF_REFERENCES,
    NOT_MEMBERDEF_COLUMNS,
    DefinitionChanges,
    FastRefusal,
    add_definitions,
    end_module_row,
    reconcile,
    remove_definitions,
)
from .indexcache import IndexCache

## Re-exported: the reference columns a removed function cascades through (pinned by a test).
__all__ = ["MEMBERDEF_REFERENCES", "NOT_MEMBERDEF_COLUMNS"]

## At most this many edited files take the fast tier; more is a full build.
FAST_MAX_FILES = 4

## The `build_meta` section the fast tier writes and `db_status` reads.
FAST_META_PREFIX = "fast."

## Whole-index layers a fast refresh leaves describing the pre-edit tree. Named in `fast.layers`
## so the `derived` notice says exactly what not to trust yet.
STALE_LAYERS = (
    ## Phase 5 refreshes the edited files' outgoing AST call edges; what stays whole-index of
    ## the call graph is doxygen's own call layer and the two global prunes.
    "doxygen_call_edges",
    "call_edge_prunes",
    "callback_edges",
    "code_text",
    "locks",
    "threads",
    "reachability",
    "context_conflicts",
    "shared_key_edges",
    "macro_refs",
    "unresolved_inbound",
    "coverage",
    "py_docstrings",
    ## PR0 (2.0.0): found by `tests/test_fast_tier_layers.py`, which classifies every table of a
    ## built index. These change with a one-file edit and the fast tier does not rewrite them, so
    ## they were stale after a save while reading as current. Named, so the notice says so.
    "doxygen_signatures",
    "includes",
    "kconfig_gates",
    "config_defaults",
    "req_edges",
    ## F1-mm (2.0.0): per-file, but the full build's rows are what the rarity gate counts over.
    "property_keys",
)

## How every table of an index stands after a fast refresh (PR0, 2.0.0): FAST (rewritten for the
## edited files), a STALE_LAYERS name (left as it was, named on every reply until the full
## refresh), or UNAFFECTED (cannot change under the fast tier's own preconditions — the same file
## set, the same definition set, no configuration input edited). A table with no class fails
## `tests/test_fast_tier_layers.py`, so a new layer cannot go silently stale.
FAST = "fast"
UNAFFECTED = "unaffected"
TABLE_CLASSES: dict[str, str] = {
    ## Rewritten in place for the edited files.
    "memberdef": FAST,
    "compounddef": FAST,
    "decl_extent": FAST,
    "file_docs": FAST,
    "generated_files": FAST,
    "supplementary_docs": FAST,
    "req_mentions": FAST,
    "call_edges": FAST,  # outgoing AST edges; doxygen's own rows are `doxygen_call_edges`
    "code_text": FAST,
    "code_text_files": FAST,
    "blocking_calls": FAST,
    "build_meta": FAST,
    "file_licenses": FAST,
    "kerneldoc": FAST,
    ## Left as they were, and named.
    "xrefs": "doxygen_call_edges",
    "memberdef_param": "doxygen_signatures",
    "param": "doxygen_signatures",
    "reimplements": "doxygen_signatures",
    "locks": "locks",
    "lock_acquisitions": "locks",
    "critical_section_calls": "locks",
    "threads": "threads",
    "thread_membership": "threads",
    "symbol_liveness": "reachability",
    "context_conflicts": "context_conflicts",
    "shared_key_edges": "shared_key_edges",
    "unresolved_inbound": "unresolved_inbound",
    "includes": "includes",
    "property_keys": "property_keys",
    "ast_includes": FAST,  # T3 served (2.0.0): the edited files' directives are re-read
    "kconfig_gates": "kconfig_gates",
    "config_defaults": "config_defaults",
    "req_edges": "req_edges",
    "req_test_edges": "req_edges",
    ## Unchanged by an edit the fast tier accepts.
    "path": UNAFFECTED,  # the file set is unchanged
    "external_boundaries": UNAFFECTED,  # likewise
    "test_scope": UNAFFECTED,  # path globs over that file set
    "refid": UNAFFECTED,  # the definition set is unchanged
    "member": UNAFFECTED,
    "contains": UNAFFECTED,
    "compoundref": UNAFFECTED,
    "requirements": UNAFFECTED,  # the catalog is a configuration input (refused, W13)
    "requirement_links": UNAFFECTED,
    "data_model_keys": UNAFFECTED,  # the data model is a configuration input
    "meta": UNAFFECTED,  # doxygen's own run record
    ## Read from CODEOWNERS / MAINTAINERS, which are not indexed source: an indexed-file edit
    ## cannot change it. (An edit to those files is picked up by the next full build.)
    "owners": UNAFFECTED,
}

## Files whose edit changes how the WHOLE tree is indexed. Matched on the basename.
_CONFIG_NAMES = frozenset(
    {
        ".clew.yaml",
        "Doxyfile",
        "requirements.yaml",
        "toolchain.toml",
        "suppress.toml",
        "pyproject.toml",
        "Kconfig",
        "CMakeLists.txt",
        ".gitmodules",
        ".gitignore",
    }
)

## Extensions the JS/TS definitions harvester anchors; C, C++ and Python use the AST one.
_JS_SUFFIXES = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")
_AST_SUFFIXES = (".c", ".h", ".cc", ".cpp", ".cxx", ".hh", ".hpp", ".hxx", ".py")

## Payload keys of the AST harvester, with the index of the line field(s) in each record.
_AST_LINE_FIELDS = {
    "functions": (4, 5),
    "variables": (4,),
    "typedefs": (4,),
    "macros": (3,),
    "enumerators": (3,),
    "class_fields": (3,),
}
## Payload keys of the JS harvester; each record is a dict with `line` and usually `end`.
_JS_KINDS = ("functions", "classes", "variables")


## @brief The outcome of a fast refresh.
## @version 1
@dataclass(frozen=True)
class FastResult:
    """@brief Files refreshed in place, the stale layers, and the cost. @version 1"""

    files: tuple[str, ...]
    layers: tuple[str, ...]
    ms: int


## @brief Try the fast tier; refresh in place and return what was done, or None for a full build.
## @param db The live index.
## @param repo_root The working tree.
## @param cache_path The index cache sidecar.
## @return A FastResult, or None when the fast tier does not apply.
## v2 (phase 6): reports the layers this refresh actually left stale.
## v3 (2.0.0, PR1): a reconciliation that cannot be exact rolls back and builds in full.
## v4 (2.0.0, owner 2026-11-20): takes the build lock, without waiting. The fast tier writes the
## shared index cache and the live index, so without the lock it declines and the caller's full
## build waits for the holder (tests/test_build_shared_state.py).
## @version 4
## @req REQ-DDB-INDEX-006
def try_fast_refresh(db: Path, repo_root: Path, cache_path: Path) -> FastResult | None:
    """NONE IS THE SAFE ANSWER: every precondition that fails returns None and the caller builds
    in full, so the worst a wrong refusal costs is time. The reason is logged at INFO.

    @brief Fast in-place refresh entry point, under the build lock.
    @return Result or None.
    @version 2
    """
    with build_lock(db, wait_seconds=0) as held:
        if held is False:
            logger.info("fast tier: not applicable — another process holds the build lock")
            return None
        return _fast_refresh_locked(db, repo_root, cache_path)


## @brief The fast tier itself, run by `try_fast_refresh` once the build lock is settled.
## @param db The live index.
## @param repo_root The working tree.
## @param cache_path The index cache sidecar.
## @return A FastResult, or None when the fast tier does not apply.
## v1 (2.0.0): the body `try_fast_refresh` had at its v3, moved unchanged.
## @version 1
## @req REQ-DDB-INDEX-006
def _fast_refresh_locked(db: Path, repo_root: Path, cache_path: Path) -> FastResult | None:
    """@brief Refresh in place, or decline. @return Result or None."""
    started = time.perf_counter()
    if not (db.is_file() and cache_path.is_file()) or not _current_build(db):
        logger.info("fast tier: not applicable — no current index or no index cache")
        return None
    cache = IndexCache(cache_path, repo_root)
    try:
        ## AUTOCOMMIT MODE, so `_apply`'s explicit BEGIN IMMEDIATE owns the one transaction.
        conn = sqlite3.connect(str(db), timeout=30, isolation_level=None)
        try:
            plans = _plan(conn, repo_root, cache)
            if plans is None:
                return None
            try:
                layers = _apply(conn, repo_root, cache, plans, started)
            except FastRefusal as refusal:
                ## ROLLED BACK by `_apply`; the index is exactly as it was.
                logger.info("fast tier: not applicable — %s", refusal)
                return None
        finally:
            conn.close()
        cache.flush()
    finally:
        cache.close()
    ms = int((time.perf_counter() - started) * 1000)
    files = tuple(sorted(plans))
    logger.info("fast tier: refreshed %s in place in %d ms", ", ".join(files), ms)
    return FastResult(files=files, layers=layers, ms=ms)


## @brief Whether the index was stamped by this build version.
## @param db The index.
## @return True when current.
## @version 1
## @utility
def _current_build(db: Path) -> bool:
    """@brief Compare the stamped build version. @return True when it matches."""
    from .signature import CLEW_BUILD_VERSION, read_build_signature

    return read_build_signature(db) == CLEW_BUILD_VERSION


## @brief The line map for every edited file, or None when any one refuses the fast tier.
## @param conn Open index connection.
## @param repo_root The working tree.
## @param cache The index cache.
## @return {repo-relative path: (path rowid, old anchors, new anchors, old sha)} or None.
## v2 (phase 6): each plan carries the old content sha, the key to the corpus texts it replaces.
## v3: a declared whole-index input refuses the fast tier (2.0.0, R5-CFG W13)
## v4: passes the repository root to _line_anchors (2.0.0)
## v5: each plan carries the file's function changes (2.0.0, PR1)
## @version 5
## @utility
def _plan(
    conn: sqlite3.Connection, repo_root: Path, cache: IndexCache
) -> dict[str, tuple[int, list[int], list[int], str, DefinitionChanges]] | None:
    """@brief Find the edited files and map each one's lines. @return Plans or None."""
    edited = _edited_files(conn, repo_root, cache)
    refusal = _refusal(edited, config_inputs(repo_root))
    if refusal:
        logger.info("fast tier: not applicable — %s", refusal)
        return None
    plans: dict[str, tuple[int, list[int], list[int], str, DefinitionChanges]] = {}
    for rowid, rel, old_sha in edited:
        anchors = _line_anchors(rel, repo_root / rel, old_sha, cache, repo_root)
        if anchors is None:
            return None
        plans[rel] = (rowid, anchors[0], anchors[1], old_sha, anchors[2])
    return plans


## @brief The content sha a pending fast refresh recorded for each file it refreshed.
## @param conn Open index connection.
## @return {repo-relative path: sha}; empty when no fast refresh is pending.
## @version 1
## @utility
def _fast_bases(conn: sqlite3.Connection) -> dict[str, str]:
    """A full build writes a fresh database, so a base can only be one a pending fast refresh
    left. Read only while `fast.pending` is 1, for the same reason `_record` accumulates.

    @brief Read the fast baselines.
    @return Shas by file.
    """
    pending = conn.execute(
        "SELECT value FROM build_meta WHERE key = ?", (f"{FAST_META_PREFIX}pending",)
    ).fetchone()
    if not pending or pending[0] != "1":
        return {}
    prefix = f"{FAST_META_PREFIX}base."
    return {
        str(k)[len(prefix) :]: str(v)
        for k, v in conn.execute(
            "SELECT key, value FROM build_meta WHERE key LIKE ?", (f"{prefix}%",)
        )
    }


## @brief Every indexed file whose content differs from what the index last described.
## @param conn Open index connection.
## @param repo_root The working tree.
## @param cache The index cache.
## @return (path rowid, repo-relative path, old content sha) per edited file.
## v2: the baseline is a pending fast refresh's `fast.base.<file>` when there is one (2.0.0, PR1)
## @version 2
## @utility
def _edited_files(
    conn: sqlite3.Connection, repo_root: Path, cache: IndexCache
) -> list[tuple[int, str, str]]:
    """THE BASELINE IS THE CONTENT THE INDEX LAST DESCRIBED: the sha a pending fast refresh
    recorded for the file (`fast.base.<file>`), else the sha the last full build stored in the
    cache. A size/mtime prefilter skips hashing an untouched file.

    v2 (2.0.0, found by `incremental_probe fastcompare` in PR1): it was ALWAYS the full build's
    sha, so a second fast refresh of one file mapped the full build's lines onto rows the first
    had already moved (a double shift: `fetchWidget` at 6 where a full build has 4), and re-added a
    function the first had added, which crashed `clew refresh` on a `refid` UNIQUE failure.

    @brief Diff the indexed files against the index's own baseline.
    @return Edited files.
    @version 2
    """
    bases = _fast_bases(conn)
    edited: list[tuple[int, str, str]] = []
    for rowid, name in conn.execute("SELECT rowid, name FROM path WHERE type = 1"):
        rel = str(name)
        old = bases.get(rel) or cache.previous_sha(rel)
        if old is None:
            continue
        new = cache.sha_for(rel, repo_root / rel)
        if new is not None and new != old:
            edited.append((int(rowid), rel, old))
    return edited


## @brief Why a set of edited files cannot take the fast tier, or "" when it can.
## @param edited The edited files.
## @return The refusal reason, or "".
## v2: a declared whole-index input refuses the fast tier (2.0.0, R5-CFG W13)
## @version 2
## @utility
def _refusal(edited: list[tuple[int, str, str]], declared: frozenset[str] = frozenset()) -> str:
    """@brief Apply the file-set preconditions. @return Reason or ""."""
    if not edited:
        return "no indexed file has changed"
    if len(edited) > FAST_MAX_FILES:
        return f"{len(edited)} files changed, more than {FAST_MAX_FILES}"
    config = [
        rel for _r, rel, _s in edited if PurePosixPath(rel).name in _CONFIG_NAMES or rel in declared
    ]
    if config:
        return f"a configuration input changed ({', '.join(config)})"
    return ""


## @brief The whole-index inputs a repository DECLARES by path, repo-relative.
## @param repo_root The repository.
## @return The declared catalog, needs import, test mapping, enrichment, data model and Doxyfile.
## @version 1
## @req REQ-DDB-INDEX-006
def config_inputs(repo_root: Path) -> frozenset[str]:
    """R5-CFG W13 (2.0.0): the fast tier refused on a config edit by BASENAME only, so a catalog
    declared at `docs/reqs.yaml` changed under it without the full build its derived requirement
    rows need. A declaration that cannot be read contributes nothing here; the full build reports
    it.

    @brief Declared whole-index inputs.
    @return Paths.
    """
    from .declaration import load_declaration
    from .vocabulary import DeclarationError

    try:
        decl = load_declaration(repo_root)
    except DeclarationError:
        return frozenset()
    reqs = decl.get("requirements") or {}
    tests = decl.get("tests") or {}
    found = [
        reqs.get("file"),
        reqs.get("needs"),
        tests.get("mapping"),
        decl.get("enrich"),
        decl.get("data_model"),
        decl.get("doxyfile"),
    ]
    return frozenset(PurePosixPath(str(f)).as_posix() for f in found if isinstance(f, str) and f)


## @brief The before/after line anchors of one file, from its old cached payload and a new parse.
## @param rel Repo-relative path.
## @param path Absolute path.
## @param old_sha The content sha the last full build recorded.
## @param cache The index cache.
## @return (old anchor lines, new anchor lines), aligned; None when the file refuses.
## v2: one shared parse warms both the anchor and the call-site payloads.
## v3: and the blocking-call payload.
## v4: the blocking harvester is the repository's declared one (2.0.0, C1)
## v5: function changes are reconciled, not refused (2.0.0, PR1)
## @version 5
## @utility
def _line_anchors(
    rel: str, path: Path, old_sha: str, cache: IndexCache, repo_root: Path | None = None
) -> tuple[list[int], list[int], DefinitionChanges] | None:
    """THE SAME HARVESTER ON BOTH SIDES, so the two anchor lists measure lines identically. The
    definitions must be the same SET in the same ORDER; anything else is a changed definition
    set, which the fast tier refuses rather than guesses at.

    @brief Build one file's line map.
    @return Aligned anchors or None.
    @version 1
    """
    from .blocking import declared_blocking_harvester
    from .call_edges import call_site_harvester
    from .harvest import HarvestTally, _cached_payload, _harvest_one_file, _shared_parse_one_file

    harvester = _anchor_harvester(rel)
    if harvester is None:
        logger.info("fast tier: not applicable — no anchor harvester for %s", rel)
        return None
    ## ONE PARSE FOR BOTH PAYLOADS the fast tier reads (anchors here, call sites in phase 5):
    ## the shared-parse helper warms every harvester it is given off a single tree.
    _shared_parse_one_file(
        rel,
        path,
        [harvester, call_site_harvester(), declared_blocking_harvester(repo_root or path.parent)],
        {},
        cache,
        HarvestTally(),
    )
    old_payload = _cached_payload(harvester, cache, old_sha)
    new_payload = _harvest_one_file(rel, path, harvester, {}, cache, HarvestTally())
    if old_payload is None or new_payload is None:
        logger.info("fast tier: not applicable — no cached parse of %s's previous content", rel)
        return None
    old, new = _anchors(rel, old_payload), _anchors(rel, new_payload)
    ## PR1 (2.0.0): an added, removed or renamed FUNCTION is reconciled; any other change refuses.
    plan = reconcile(rel.lower().endswith(_JS_SUFFIXES), old_payload, new_payload, old, new)
    if plan is None:
        logger.info("fast tier: not applicable — %s's non-function definitions changed", rel)
    return plan


## @brief The harvester whose payload anchors a file's lines.
## @param rel Repo-relative path.
## @return The harvester, or None for a language the fast tier does not anchor.
## @version 1
## @utility
def _anchor_harvester(rel: str) -> Any:
    """@brief Pick JS or AST anchors by extension. @return Harvester or None."""
    from .ast_symbols import function_definition_harvester
    from .synth import js_symbol_harvester

    lowered = rel.lower()
    if lowered.endswith(_JS_SUFFIXES):
        return js_symbol_harvester()
    if lowered.endswith(_AST_SUFFIXES):
        return function_definition_harvester()
    return None


## @brief Every (identity, line) anchor in a payload, in a stable order.
## @param rel Repo-relative path, selecting the payload shape.
## @param payload A harvester payload.
## @return [((kind, name, field, ordinal), line), ...] sorted by kind, name, ordinal.
## @version 1
## @utility
def _anchors(rel: str, payload: Any) -> list[tuple[tuple[Any, ...], int]]:
    """KEYED BY IDENTITY, NOT POSITION, with an ordinal for repeated names: two payloads align
    only when they hold the same definitions, which is the precondition being tested.

    @brief Flatten a payload into anchors.
    @return Anchors.
    @version 1
    """
    out: list[tuple[tuple[Any, ...], int]] = []
    seen: dict[tuple[Any, ...], int] = {}
    for kind, name, field, line in _records(rel, payload):
        base = (kind, name, field)
        seen[base] = seen.get(base, 0) + 1
        out.append(((*base, seen[base]), int(line)))
    return sorted(out, key=lambda item: item[0])


## @brief The (kind, name, field, line) facts of one payload.
## @param rel Repo-relative path.
## @param payload A harvester payload.
## @return The facts.
## @version 1
## @utility
def _records(rel: str, payload: Any) -> list[tuple[str, str, int, int]]:
    """@brief Read line facts out of either payload shape. @return Facts."""
    facts: list[tuple[str, str, int, int]] = []
    if not isinstance(payload, dict):
        return facts
    if rel.lower().endswith(_JS_SUFFIXES):
        for kind in _JS_KINDS:
            for record in payload.get(kind) or []:
                name = f"{record.get('cls') or ''}.{record.get('name')}"
                facts.append((kind, name, 0, int(record.get("line") or 0)))
                if record.get("end"):
                    facts.append((kind, name, 1, int(record["end"])))
        return facts
    for kind, fields in _AST_LINE_FIELDS.items():
        for record in payload.get(kind) or []:
            for which, index in enumerate(fields):
                facts.append(
                    (
                        kind,
                        str(record[1] if kind == "functions" else record[0]),
                        which,
                        int(record[index]),
                    )
                )
    return facts


## @brief Map one old line to its new line.
## @param line The old line.
## @param old Old anchor lines, ascending.
## @param new The aligned new anchor lines.
## @return The new line.
## @version 1
## @utility
def remap_line(line: int, old: list[int], new: list[int]) -> int:
    """THE NEAREST ANCHOR AT OR ABOVE THE LINE carries it: everything between two definitions
    moved with the one above. A line above the first anchor (a file header) did not move. Zero —
    "no line" in every table here — stays zero.

    @brief Remap a line.
    @return The new line.
    @version 1
    """
    if line <= 0:
        return line
    at = bisect.bisect_right(old, line) - 1
    return line if at < 0 else line + (new[at] - old[at])


## @brief Apply every plan and the text layers, and record the fast refresh, in one transaction.
## @param conn Open index connection.
## @param repo_root The working tree.
## @param cache The index cache.
## @param plans Per-file line maps.
## @param started perf_counter at the start, for the recorded cost.
## @return The layers left stale.
## v2 (1.3.5 phase 5): re-folds the edited files' outgoing AST call edges after the shift.
## v3 (phase 6): replaces the edited files' code-corpus rows; returns the stale layers.
## v4 (phase 6): and their blocking call sites.
## v5: and their #include rows (2.0.0, T3 served)
## v6: and their added and removed functions (2.0.0, PR1)
## v7: and each file's new baseline sha, `fast.base.<file>` (2.0.0, PR1)
## v8: and a JS/TS file's `__module__` row ends at its new last line (2.0.0, PR1)
## @version 8
## @utility
def _apply(
    conn: sqlite3.Connection,
    repo_root: Path,
    cache: IndexCache,
    plans: dict[str, tuple[int, list[int], list[int], str, DefinitionChanges]],
    started: float,
) -> tuple[str, ...]:
    """ONE TRANSACTION, `BEGIN IMMEDIATE`, so a reader sees the index before or after the whole
    refresh and never between two files of it.

    v2 (phase 5): also replaces the edited files' outgoing AST call edges.
    v3 (phase 6): and their code-corpus rows; the corpus is named stale only if that failed.
    v4: and their blocking call sites.
    v6 (PR1): removed functions are deleted BEFORE the shift (their rows still sit at the old
    lines) and added ones written AFTER it (at the new lines), both before the call-edge and
    corpus refreshes, which read `memberdef`. A `FastRefusal` rolls the whole refresh back.

    @brief Write the fast refresh.
    @return The layers left stale.
    @version 8
    """
    from .code_text import code_text_rows
    from .ast_includes import refresh_ast_includes
    from .fasttier_calls import refresh_blocking_calls, refresh_outbound_calls
    from .fasttier_layers import refresh_code_text, refresh_text_layers

    conn.execute("BEGIN IMMEDIATE")
    try:
        ## The corpus rows BEFORE the shift: their old spans are the old texts' cache key.
        before = {rel: code_text_rows(conn, rel) for rel in plans}
        provisional: list[str] = []
        for rel, (rowid, old, new, _sha, changes) in plans.items():
            js = rel.lower().endswith(_JS_SUFFIXES)
            remove_definitions(conn, rowid, js, changes.removed)
            _shift_symbols(conn, rowid, old, new)
            end_module_row(conn, rowid, changes.module_lines)
            provisional += add_definitions(conn, rowid, rel, js, changes.added)
            refresh_text_layers(conn, repo_root, rel, cache)
        ## AFTER EVERY SHIFT: the fold places each call site by the spans it now reads.
        files = {rel: p[0] for rel, p in plans.items()}
        maps = refresh_outbound_calls(conn, repo_root, cache, files)
        refresh_blocking_calls(conn, repo_root, cache, files, maps["file_funcs"])
        refresh_ast_includes(conn, repo_root, cache, files)
        corpus_current = all(
            refresh_code_text(conn, repo_root, rel, cache, plan[3], before[rel])
            for rel, plan in plans.items()
        )
        layers = tuple(lay for lay in STALE_LAYERS if lay != "code_text" or not corpus_current)
        _record(conn, tuple(sorted(plans)), layers, started, tuple(provisional))
        ## THE NEW BASELINE for each refreshed file: the content the index now describes.
        conn.executemany(
            "INSERT OR REPLACE INTO build_meta (key, value) VALUES (?, ?)",
            [
                (f"{FAST_META_PREFIX}base.{rel}", cache.sha_for(rel, repo_root / rel) or "")
                for rel in plans
            ],
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return layers


## @brief Move one file's symbol positions through its line map.
## @param conn Open index connection.
## @param rowid The file's path rowid.
## @param old Old anchors.
## @param new New anchors.
## @return None.
## @version 1
## @utility
def _shift_symbols(conn: sqlite3.Connection, rowid: int, old: list[int], new: list[int]) -> None:
    """THE ROWS STAY, ONLY THEIR LINES MOVE, so every edge, requirement link and membership that
    points at them is still pointing at the right symbol.

    @brief Remap memberdef, compounddef and decl_extent lines for one file.
    @return None.
    @version 1
    """
    members = conn.execute(
        "SELECT rowid, line, bodystart, bodyend, file_id, bodyfile_id FROM memberdef "
        "WHERE file_id = ? OR bodyfile_id = ?",
        (rowid, rowid),
    ).fetchall()
    for mrow, line, bstart, bend, file_id, body_id in members:
        new_line = remap_line(int(line or 0), old, new) if file_id == rowid else line
        start = remap_line(int(bstart or 0), old, new) if body_id == rowid else bstart
        end = remap_line(int(bend or 0), old, new) if body_id == rowid else bend
        conn.execute(
            "UPDATE memberdef SET line = ?, bodystart = ?, bodyend = ? WHERE rowid = ?",
            (new_line, start, end, mrow),
        )
    for crow, line in conn.execute(
        "SELECT rowid, line FROM compounddef WHERE file_id = ?", (rowid,)
    ).fetchall():
        conn.execute(
            "UPDATE compounddef SET line = ? WHERE rowid = ?",
            (remap_line(int(line or 0), old, new), crow),
        )
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'decl_extent'").fetchone():
        for mrow, end_line in conn.execute(
            "SELECT d.memberdef_rowid, d.end_line FROM decl_extent d JOIN memberdef m "
            "ON m.rowid = d.memberdef_rowid WHERE m.file_id = ?",
            (rowid,),
        ).fetchall():
            conn.execute(
                "UPDATE decl_extent SET end_line = ? WHERE memberdef_rowid = ?",
                (remap_line(int(end_line or 0), old, new), mrow),
            )


## @brief The functions written with provisional rowids since the last full build.
## @param conn Open connection.
## @param names This refresh's added functions.
## @param accumulate Whether an earlier fast refresh is still pending.
## @return Comma-joined names, sorted.
## @version 1
## @utility
def _provisional(conn: sqlite3.Connection, names: tuple[str, ...], accumulate: bool) -> str:
    """PR1 (2.0.0): an added function's inbound edges wait for the full build, so the record names
    every function whose row is provisional, across every fast refresh still pending.

    @brief Accumulate provisional names.
    @return The value.
    """
    every = set(names)
    if accumulate:
        earlier = conn.execute(
            "SELECT value FROM build_meta WHERE key = ?", (f"{FAST_META_PREFIX}provisional",)
        ).fetchone()
        every.update(n for n in str(earlier[0] if earlier else "").split(",") if n)
    return ",".join(sorted(every))


## @brief Write the `fast.*` record the derived axis reads.
## @param conn Open index connection, inside the transaction.
## @param files The files refreshed.
## @param layers The layers left stale.
## @param started perf_counter at the start.
## @return None.
## v2 (phase 6): records the layers this refresh actually left stale.
## v3: records fast.provisional (2.0.0, PR1)
## @version 3
## @utility
def _record(
    conn: sqlite3.Connection,
    files: tuple[str, ...],
    layers: tuple[str, ...],
    started: float,
    provisional: tuple[str, ...] = (),
) -> None:
    """A SECOND FAST REFRESH ACCUMULATES: its files join the earlier ones, because the stale
    layers still describe the tree before the FIRST of them.

    @brief Upsert fast.* keys.
    @return None.
    @version 1
    """
    prior = conn.execute(
        "SELECT value FROM build_meta WHERE key = ?", (f"{FAST_META_PREFIX}files",)
    ).fetchone()
    pending = conn.execute(
        "SELECT value FROM build_meta WHERE key = ?", (f"{FAST_META_PREFIX}pending",)
    ).fetchone()
    every = set(files)
    stale = set(layers)
    if prior and pending and pending[0] == "1":
        every.update(f for f in str(prior[0]).split(",") if f)
        ## AND ITS STALE LAYERS: a layer an earlier fast refresh left behind is still behind.
        earlier = conn.execute(
            "SELECT value FROM build_meta WHERE key = ?", (f"{FAST_META_PREFIX}layers",)
        ).fetchone()
        stale.update(lay for lay in str(earlier[0] if earlier else "").split(",") if lay)
    generation = conn.execute(
        "SELECT value FROM build_meta WHERE key = ?", (f"{FAST_META_PREFIX}generation",)
    ).fetchone()
    values = {
        "pending": "1",
        "files": ",".join(sorted(every)),
        "layers": ",".join(lay for lay in STALE_LAYERS if lay in stale),
        "generation": str(int(generation[0]) + 1 if generation else 1),
        "ms": str(int((time.perf_counter() - started) * 1000)),
        "provisional": _provisional(
            conn, provisional, bool(prior and pending and pending[0] == "1")
        ),
    }
    conn.executemany(
        "INSERT OR REPLACE INTO build_meta (key, value) VALUES (?, ?)",
        [(f"{FAST_META_PREFIX}{k}", v) for k, v in values.items()],
    )
