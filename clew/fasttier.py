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

WHAT IT REFUSES — each refusal is a full build, never a guess:
  * a changed SET of definitions (added, removed, renamed, reordered): a new symbol needs a row,
    a rowid and edges, which only the full pipeline allocates;
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
from .indexcache import IndexCache

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
)

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
## @version 2
## @req REQ-DDB-INDEX-006
def try_fast_refresh(db: Path, repo_root: Path, cache_path: Path) -> FastResult | None:
    """NONE IS THE SAFE ANSWER: every precondition that fails returns None and the caller builds
    in full, so the worst a wrong refusal costs is time. The reason is logged at INFO.

    @brief Fast in-place refresh entry point.
    @return Result or None.
    @version 1
    """
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
            layers = _apply(conn, repo_root, cache, plans, started)
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
## @dg_internal
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
## @version 2
## @dg_internal
def _plan(
    conn: sqlite3.Connection, repo_root: Path, cache: IndexCache
) -> dict[str, tuple[int, list[int], list[int], str]] | None:
    """@brief Find the edited files and map each one's lines. @return Plans or None."""
    edited = _edited_files(conn, repo_root, cache)
    refusal = _refusal(edited)
    if refusal:
        logger.info("fast tier: not applicable — %s", refusal)
        return None
    plans: dict[str, tuple[int, list[int], list[int], str]] = {}
    for rowid, rel, old_sha in edited:
        anchors = _line_anchors(rel, repo_root / rel, old_sha, cache)
        if anchors is None:
            return None
        plans[rel] = (rowid, *anchors, old_sha)
    return plans


## @brief Every indexed file whose content differs from what the last full build recorded.
## @param conn Open index connection.
## @param repo_root The working tree.
## @param cache The index cache.
## @return (path rowid, repo-relative path, old content sha) per edited file.
## @version 1
## @dg_internal
def _edited_files(
    conn: sqlite3.Connection, repo_root: Path, cache: IndexCache
) -> list[tuple[int, str, str]]:
    """THE CACHE'S RECORD IS THE BASELINE, not the database's mtime: the sha the last full build
    stored for each file. A size/mtime prefilter skips hashing an untouched file.

    @brief Diff the indexed files against the cache's record.
    @return Edited files.
    @version 1
    """
    edited: list[tuple[int, str, str]] = []
    for rowid, name in conn.execute("SELECT rowid, name FROM path WHERE type = 1"):
        rel = str(name)
        old = cache.previous_sha(rel)
        if old is None:
            continue
        new = cache.sha_for(rel, repo_root / rel)
        if new is not None and new != old:
            edited.append((int(rowid), rel, old))
    return edited


## @brief Why a set of edited files cannot take the fast tier, or "" when it can.
## @param edited The edited files.
## @return The refusal reason, or "".
## @version 1
## @dg_internal
def _refusal(edited: list[tuple[int, str, str]]) -> str:
    """@brief Apply the file-set preconditions. @return Reason or ""."""
    if not edited:
        return "no indexed file has changed"
    if len(edited) > FAST_MAX_FILES:
        return f"{len(edited)} files changed, more than {FAST_MAX_FILES}"
    config = [rel for _r, rel, _s in edited if PurePosixPath(rel).name in _CONFIG_NAMES]
    if config:
        return f"a configuration input changed ({', '.join(config)})"
    return ""


## @brief The before/after line anchors of one file, from its old cached payload and a new parse.
## @param rel Repo-relative path.
## @param path Absolute path.
## @param old_sha The content sha the last full build recorded.
## @param cache The index cache.
## @return (old anchor lines, new anchor lines), aligned; None when the file refuses.
## v2: one shared parse warms both the anchor and the call-site payloads.
## v3: and the blocking-call payload.
## @version 3
## @dg_internal
def _line_anchors(
    rel: str, path: Path, old_sha: str, cache: IndexCache
) -> tuple[list[int], list[int]] | None:
    """THE SAME HARVESTER ON BOTH SIDES, so the two anchor lists measure lines identically. The
    definitions must be the same SET in the same ORDER; anything else is a changed definition
    set, which the fast tier refuses rather than guesses at.

    @brief Build one file's line map.
    @return Aligned anchors or None.
    @version 1
    """
    from .blocking import blocking_harvester
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
        [harvester, call_site_harvester(), blocking_harvester()],
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
    if [key for key, _line in old] != [key for key, _line in new]:
        logger.info("fast tier: not applicable — %s's set of definitions changed", rel)
        return None
    pairs = sorted({(o, n) for (_k, o), (_k2, n) in zip(old, new, strict=True)})
    return [o for o, _n in pairs], [n for _o, n in pairs]


## @brief The harvester whose payload anchors a file's lines.
## @param rel Repo-relative path.
## @return The harvester, or None for a language the fast tier does not anchor.
## @version 1
## @dg_internal
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
## @dg_internal
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
## @dg_internal
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
## @dg_internal
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
## @version 4
## @dg_internal
def _apply(
    conn: sqlite3.Connection,
    repo_root: Path,
    cache: IndexCache,
    plans: dict[str, tuple[int, list[int], list[int], str]],
    started: float,
) -> tuple[str, ...]:
    """ONE TRANSACTION, `BEGIN IMMEDIATE`, so a reader sees the index before or after the whole
    refresh and never between two files of it.

    v2 (phase 5): also replaces the edited files' outgoing AST call edges.
    v3 (phase 6): and their code-corpus rows; the corpus is named stale only if that failed.
    v4: and their blocking call sites.

    @brief Write the fast refresh.
    @return The layers left stale.
    @version 4
    """
    from .code_text import code_text_rows
    from .fasttier_calls import refresh_blocking_calls, refresh_outbound_calls
    from .fasttier_layers import refresh_code_text, refresh_text_layers

    conn.execute("BEGIN IMMEDIATE")
    try:
        ## The corpus rows BEFORE the shift: their old spans are the old texts' cache key.
        before = {rel: code_text_rows(conn, rel) for rel in plans}
        for rel, (rowid, old, new, _sha) in plans.items():
            _shift_symbols(conn, rowid, old, new)
            refresh_text_layers(conn, repo_root, rel, cache)
        ## AFTER EVERY SHIFT: the fold places each call site by the spans it now reads.
        files = {rel: p[0] for rel, p in plans.items()}
        maps = refresh_outbound_calls(conn, repo_root, cache, files)
        refresh_blocking_calls(conn, repo_root, cache, files, maps["file_funcs"])
        corpus_current = all(
            refresh_code_text(conn, repo_root, rel, cache, plan[3], before[rel])
            for rel, plan in plans.items()
        )
        layers = tuple(lay for lay in STALE_LAYERS if lay != "code_text" or not corpus_current)
        _record(conn, tuple(sorted(plans)), layers, started)
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
## @dg_internal
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


## @brief Write the `fast.*` record the derived axis reads.
## @param conn Open index connection, inside the transaction.
## @param files The files refreshed.
## @param layers The layers left stale.
## @param started perf_counter at the start.
## @return None.
## v2 (phase 6): records the layers this refresh actually left stale.
## @version 2
## @dg_internal
def _record(
    conn: sqlite3.Connection, files: tuple[str, ...], layers: tuple[str, ...], started: float
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
    }
    conn.executemany(
        "INSERT OR REPLACE INTO build_meta (key, value) VALUES (?, ?)",
        [(f"{FAST_META_PREFIX}{k}", v) for k, v in values.items()],
    )
