# SPDX-License-Identifier: MIT
"""Per-file tree-sitter parse plumbing + the cached harvest driver.

ELEVEN pipeline stages walk EVERY indexed C/C++ file's AST (kconfig gates,
recovered symbols, call edges Layer 3, callback/fnptr Layer 4, locks, declared
dispatch tables, thread spawns, inferred shared-key Layer 5a, MQTT subscribe
sites, Python `__main__` guards, macro references). That per-file work is the
pipeline's dominant cost and the only part that is genuinely incrementable: each
file's harvest depends on that file's bytes alone.

**ONE PARSE FEEDS ALL ELEVEN (gh#358).** Each stage used to drive its own
full-tree `run_harvest`, and `parser_cache` memoizes tree-sitter *Parser*
objects, not parsed trees — so a cold build parsed every file once per stage and
a release-blocking three minutes was overwhelmingly redundant.
`run_shared_parse` walks the tree ONCE before the stages, parses each file once,
and warms each stage's OWN cache row from that single tree; every stage then
finds its payload already there.

**MEMBERSHIP IS THE WHOLE MECHANISM, AND IT IS EASY TO MISS.** `macro_refs` was
absent from the plan for as long as the plan existed, so it kept driving its own
full-tree parse while every sibling read cached rows — `1 payload(s) from cache,
1548 parsed here` against the inverse everywhere else, costing 29.5 s of a 130 s
cold build. Nothing failed; the only symptom was the time. A stage outside the
plan is correct and slow, which is why the guard for this is structural
(`test_every_harvester_subclass_is_reachable_from_the_plan`) rather than a list
someone has to remember to extend.

The cache KEY IS NOT MERGED, deliberately. Each stage keeps its own
`(content_sha, stage, stage_version, extra_key)` row, so bumping one stage's
version still invalidates exactly that stage. A single combined key would be
either all-or-nothing (every routine stage edit forcing a whole-tree re-parse)
or LOSSY — a changed component the combine omitted would hash the same, serve a
merged blob, and emit one layer from stale logic while reporting a cache hit.

`Harvester` is the strong base class holding all of the shared machinery —
cache lookup, parse, store, progress, statistics — leaving each concrete stage
with a single `harvest(tree, src_bytes)` method.

**Payloads must be rowid-FREE.** doxygen assigns `memberdef.rowid` afresh on
every run, so a cached payload records source LINE numbers and identifier text;
every stage re-resolves those to rowids against the current database on every
build (via `call_edges._ast_caller_at_line` / the name indexes). Cross-file
stages — reachability, thread membership, boundary annotation, requirements —
are never cached: they depend on the whole assembled graph and are cheap.

@brief Per-file AST parse + content-addressed harvest driver.
@version 3
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._common import logger, make_progress
from .indexcache import IndexCache

_CPP_EXTS = (".cpp", ".cc", ".cxx", ".c++", ".hpp", ".hh", ".hxx", ".h++")
_C_EXTS = (".c", ".h")
# doxygen indexes Python too, so a Python codebase already had memberdefs, prose and
# doxygen call_edges — but NO tree-sitter layer, because this router returned
# None for `.py` and every AST stage silently skipped the file. Measured on
# clew's own 81-file index before routing: 1082 call_edges, of which 0 were
# `ast`/`ast_member`, and 0 threads. `.pyi` is included because a stub carries
# real signatures; it contributes no call sites, which is correct rather than a
# gap.
_PY_EXTS = (".py", ".pyi")
# Doxygen has no Rust parser at all, so `.rs` files get zero doxygen coverage
# regardless of this router — clew/rustdoc.py fills that gap from rustdoc JSON
# instead (see its module docstring). This grammar entry is what gives a Rust
# repo the SAME tree-sitter richness layers (call edges, threads, locks) a
# doxygen-sourced C/C++/Python repo already gets.
_RUST_EXTS = (".rs",)
# Extension group → grammar module, in PRECEDENCE order: the C++ suffixes are
# tried first so `.hpp`/`.h++` never fall through to the C grammar. A table
# rather than an if-chain because the house limit is three returns per function
# and adding Python made the fourth.
_TS_GRAMMARS: tuple[tuple[tuple[str, ...], str], ...] = (
    (_CPP_EXTS, "tree_sitter_cpp"),
    (_C_EXTS, "tree_sitter_c"),
    (_PY_EXTS, "tree_sitter_python"),
    (_RUST_EXTS, "tree_sitter_rust"),
)


## @brief Import a tree-sitter grammar module by name, or None if absent.
## @return The imported grammar module, or None when it isn't installed.
## @version 1
## @dg_internal
def _try_import_ts_module(modname: str):
    try:
        return __import__(modname)
    except ImportError:
        return None


## @brief Select the C, C++, Python or Rust tree-sitter language by extension.
## @return The grammar module for the path's extension, or None if unhandled.
## @version 4
## @dg_internal
def _ts_language_for(path: str):
    """Select the tree-sitter grammar for one path's extension.

    Python is routed here rather than at each stage so that EVERY cacheable AST
    stage sees `.py` files at once — the per-file harvest driver gates on this
    function twice (`_harvest_one_file`'s early-out and `_ast_parse_one_file`),
    so a stage cannot opt in on its own.

    Order matters and is carried by `_TS_GRAMMARS`: `.h` is checked after the C++
    list so an ambiguous header still lands on C first and is retried per
    `_AMBIGUOUS_EXTS`.

    @brief Grammar module for one path.
    @version 3
    """
    lower = path.lower()
    modname = next((m for exts, m in _TS_GRAMMARS if lower.endswith(exts)), None)
    return _try_import_ts_module(modname) if modname is not None else None


# `.h` says nothing about the language: C uses it, and so does every C++ project
# following the Google style guide. Routing it to C unconditionally does not
# merely fail on a C++ header — it FABRICATES structure. Measured on a header
# with a namespace + class + mutable std::mutex member + template function:
# the C grammar yields 7 ERROR/MISSING nodes and reports TWO function
# definitions where one exists; the C++ grammar yields 0 errors and one.
_AMBIGUOUS_EXTS = (".h",)

## How many files the shared parse may process before flushing payload rows to the sidecar.
##
## A DURABILITY INTERVAL, NOT A BATCH SIZE — nothing accumulates in memory waiting for it, and
## raising it buys no throughput. It bounds how much parsing a killed build throws away: at 500
## files a kill loses at most the tail, against the whole pass before #505. Low enough that a
## large corpus banks steadily, high enough that the commits are lost in the noise of parsing
## (one fsync per 500 tree-sitter parses).
_FLUSH_EVERY = 500


## @brief Memoized tree-sitter parser for one grammar module name.
## @param mod_name Grammar module to load ("tree_sitter_c" / "tree_sitter_cpp").
## @param parser_cache Mutated in place to memoize parsers per grammar.
## @param Parser tree_sitter Parser class.
## @param Language tree_sitter Language class.
## @return A Parser, or None when the grammar module is not installed.
## @version 1
## @dg_internal
def _cached_parser(mod_name: str, parser_cache: dict, Parser, Language):
    """@brief Build (once) and return the parser for a grammar module."""
    parser = parser_cache.get(mod_name)
    if parser is None:
        mod = _try_import_ts_module(mod_name)
        parser = Parser(Language(mod.language())) if mod is not None else None
        parser_cache[mod_name] = parser
    return parser


## @brief Count ERROR/MISSING nodes in a parsed tree.
## @param root Tree-sitter root node.
## @return Number of ERROR or missing nodes in the subtree.
## @version 1
## @dg_internal
def _parse_error_count(root) -> int:
    """@brief Total ERROR/MISSING nodes, used to compare two candidate grammars."""
    errors = 0
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "ERROR" or node.is_missing:
            errors += 1
        stack.extend(node.children)
    return errors


## @brief Re-parse an erroring ambiguous header as C++ and keep the cleaner tree.
## @param c_tree The tree produced by the C grammar.
## @param src_bytes Raw file bytes.
## @param parser_cache Parser memo.
## @param Parser tree_sitter Parser class.
## @param Language tree_sitter Language class.
## @return Whichever tree has fewer parse errors.
## @version 1
## @dg_internal
def _disambiguate_header(c_tree, src_bytes: bytes, parser_cache: dict, Parser, Language):
    """Only reached for a `.h` whose C parse ALREADY errored, so a genuine C
    header never pays for this. Comparing error counts (rather than demanding
    zero) keeps the right grammar for a C++ header that also trips on macros.
    Ties keep C, so nothing changes unless C++ is strictly better.
    """
    cpp = _cached_parser("tree_sitter_cpp", parser_cache, Parser, Language)
    if cpp is None:
        return c_tree
    cpp_tree = cpp.parse(src_bytes)
    if _parse_error_count(cpp_tree.root_node) < _parse_error_count(c_tree.root_node):
        return cpp_tree
    return c_tree


## @brief Parse one file with the appropriate tree-sitter grammar.
## @return (tree, src_bytes), or None for an unhandled/unreadable file.
## @version 3
## @dg_internal
def _ast_parse_one_file(
    rel_path: str,
    abs_path: Path,
    parser_cache: dict,
    Parser,
    Language,
) -> tuple[Any, bytes] | None:
    """Parse one file with the appropriate tree-sitter grammar.

    Returns (tree, src_bytes) on success or None when the file's extension
    isn't recognized, the file isn't a regular file, or the read failed.
    `parser_cache` is mutated in place to memoize per-language parsers.

    A `.h` that fails to parse as C is retried as C++ (see _AMBIGUOUS_EXTS).

    @brief Parse one source file into a tree-sitter tree.
    @version 3
    """
    lang_mod = _ts_language_for(rel_path)
    parser = (
        _cached_parser(lang_mod.__name__, parser_cache, Parser, Language)
        if lang_mod is not None
        else None
    )
    if parser is None or not abs_path.is_file():
        return None
    try:
        src_bytes = abs_path.read_bytes()
    except OSError:
        return None
    tree = parser.parse(src_bytes)
    if rel_path.lower().endswith(_AMBIGUOUS_EXTS) and tree.root_node.has_error:
        tree = _disambiguate_header(tree, src_bytes, parser_cache, Parser, Language)
    return tree, src_bytes


## @brief Try importing tree_sitter's Language/Parser classes.
## @return (Language, Parser), or None if tree_sitter isn't installed.
## @version 2
## @req REQ-DDB-PIPE-003
def try_import_tree_sitter() -> tuple[Any, Any] | None:
    """Return (Language, Parser), or None if tree_sitter isn't importable.

    @brief Optional tree_sitter import.
    @version 2
    """
    try:
        from tree_sitter import (  # type: ignore[import-not-found]
            Language,
            Parser,
        )
    except ImportError:
        return None
    return Language, Parser


## @brief Nearest enclosing node of one of the given types.
## @param node Starting node (its own type is NOT considered).
## @param types Node types to look for.
## @return The nearest matching ancestor, or None.
## @version 1
## @req REQ-DDB-PIPE-003
def enclosing(node: Any, types: tuple[str, ...]) -> Any:
    """Walks the PARENT chain, so a node is never its own ancestor — the section
    walk relies on that to find the block a `compound_statement` release sits
    inside rather than the release's own body.

    @brief Walk up to the first ancestor of a wanted type.
    @version 1
    """
    current = node.parent
    while current is not None and current.type not in types:
        current = current.parent
    return current


## @brief Base class for a cacheable per-file AST extraction stage.
## @version 1
class Harvester:
    """One per-file AST extraction stage.

    Subclasses set `stage` (the `extract_cache` stage tag), bump
    `stage_version` whenever their extraction LOGIC changes (the version is
    part of the cache key, so a bump invalidates that stage and nothing else),
    optionally pass an `extra_key` folding a manifest's content hash into the
    key, and implement `harvest`.

    @brief Cacheable per-file AST extraction stage.
    @version 1
    """

    stage: str = ""
    stage_version: int = 1
    label: str = "ast harvest"

    ## @brief Store the manifest-derived extra cache-key component.
    ## @version 1
    ## @dg_internal
    def __init__(self, extra_key: str = "") -> None:
        self.extra_key = extra_key

    ## @brief Extract this stage's rowid-free facts from one parsed file.
    ## @return A JSON-serializable payload for this file.
    ## @version 1
    ## @req REQ-DDB-PIPE-003
    def harvest(self, tree: Any, src_bytes: bytes) -> Any:
        """Subclass hook. MUST return JSON-serializable, rowid-free data.

        @brief Per-file extraction hook.
        @version 1
        """
        raise NotImplementedError


## @brief Per-stage record of how a whole-index harvest was served.
## @version 1
@dataclass
class HarvestTally:
    """How many of a stage's per-file payloads came from cache and how many were
    computed here, plus how many files this pass actually PARSED.

    `cached` + `computed` counts payloads (one per file per stage); `parsed`
    counts files that reached the tree-sitter parser. On a shared pass the two
    differ by design — one parse can produce several stages' payloads — and that
    gap IS the gh#358 saving, so it is reported rather than inferred.

    @brief Cache-hit / parse accounting for one harvest pass.
    @version 1
    """

    cached: int = 0
    computed: int = 0
    parsed: int = 0


## @brief Serve one file's payload from cache, or parse + harvest + store it.
## @return The file's payload, or None when the file isn't parseable.
## @version 3
## @dg_internal
def _harvest_one_file(
    rel_path: str,
    abs_path: Path,
    harvester: Harvester,
    parser_cache: dict,
    ts_classes: tuple[Any, Any],
    cache: IndexCache | None,
    tally: HarvestTally,
) -> Any | None:
    """Cache lookup is keyed on the file's content sha, so an unchanged file
    never re-parses and a modified file always does. A file whose sha can't be
    computed simply parses (fail toward the MISS).

    @brief Cached single-file harvest.
    @version 2
    """
    # Non-source paths and paths doxygen recorded but that don't exist under
    # the repo root (system headers it followed) never reach the parser, so
    # they never reach the cache either.
    if _ts_language_for(rel_path) is None or not abs_path.is_file():
        return None
    sha = cache.sha_for(rel_path, abs_path) if cache is not None else None
    hit = _cached_payload(harvester, cache, sha)
    if hit is not None:
        tally.cached += 1
        return hit
    tally.computed += 1
    return _parse_and_store(rel_path, abs_path, harvester, parser_cache, ts_classes, cache, sha)


## @brief This file's cached payload for this harvester stage, if any.
## @param harvester The stage being served.
## @param cache Live index cache, or None.
## @param sha The file's content sha, or None when it could not be computed.
## @return The cached payload, or None on a miss.
## @version 2
## @dg_internal
def _cached_payload(harvester: Harvester, cache: IndexCache | None, sha: str | None) -> Any | None:
    """A file whose sha cannot be computed always misses — fail toward
    re-parsing rather than serving a payload that may describe other bytes.

    Accounting goes through `record_pair`, which counts each (file, stage) pair
    ONCE per build. Since gh#358 a payload is usually computed by the shared
    parse pass and then read back here, and counting both would report a cold
    build as thousands of cache HITS — the reading a user would take as "nothing
    was reprocessed".

    @brief Look up one file's cached stage payload.
    @return Payload or None.
    @version 2
    """
    if cache is None or not sha:
        return None
    hit = cache.extract_get(sha, harvester.stage, harvester.stage_version, harvester.extra_key)
    if hit is not None:
        cache.record_pair(sha, harvester.stage, harvester.stage_version, harvester.extra_key, True)
    return hit


## @brief Parse one file, run the harvester, and store the result.
## @param rel_path Repo-relative path (selects the grammar).
## @param abs_path Absolute path to read.
## @param harvester The stage to run.
## @param parser_cache Per-language parser memo.
## @param ts_classes (Language, Parser) from tree_sitter.
## @param cache Live index cache, or None.
## @param sha The file's content sha, or None.
## @return The harvested payload, or None when the file is not parseable.
## @version 2
## @dg_internal
def _parse_and_store(
    rel_path: str,
    abs_path: Path,
    harvester: Harvester,
    parser_cache: dict,
    ts_classes: tuple[Any, Any],
    cache: IndexCache | None,
    sha: str | None,
) -> Any | None:
    """@brief Parse, harvest, and cache one file's payload.

    @version 2
    """
    language_cls, parser_cls = ts_classes
    parsed = _ast_parse_one_file(rel_path, abs_path, parser_cache, parser_cls, language_cls)
    if parsed is None:
        return None
    payload = harvester.harvest(parsed[0], parsed[1])
    if cache is not None and sha:
        _store_payload(cache, harvester, sha, payload)
    return payload


## @brief Write one stage payload to the cache and account for the miss once.
## @param cache Live index cache.
## @param harvester The stage whose payload this is.
## @param sha The file's content sha.
## @param payload The rowid-free payload to store.
## @version 1
## @dg_internal
def _store_payload(cache: IndexCache, harvester: Harvester, sha: str, payload: Any) -> None:
    """Single write path shared by the per-stage driver and the shared parse pass,
    so a payload stored by either is keyed and counted identically.

    @brief Store + account for one computed stage payload.
    @version 1
    """
    cache.extract_put(sha, harvester.stage, harvester.stage_version, harvester.extra_key, payload)
    cache.record_pair(sha, harvester.stage, harvester.stage_version, harvester.extra_key, False)


## @brief Run one harvester over every indexed file, cache-first.
## @return List of (path_rowid, payload) in `path`-table order.
## @version 3
## @req REQ-DDB-PIPE-003
def run_harvest(
    conn: sqlite3.Connection,
    repo_root: Path,
    harvester: Harvester,
    ts_classes: tuple[Any, Any],
    cache: IndexCache | None = None,
) -> list[tuple[int, Any]]:
    """Iterate the `path` table in rowid order (so edge insertion order — and
    therefore the INSERT OR IGNORE dedup outcome — is identical whether the
    payloads came from a fresh parse or the cache) and collect each file's
    harvest payload.

    Since gh#358 the payloads are normally already in the cache, put there by
    `run_shared_parse` off ONE parse of each file, so this walk is a sequence of
    sqlite reads. It still parses whatever it cannot find, which is what makes
    the shared pass an optimization rather than a dependency: a stage whose
    harvester the shared pass never saw (or a build with no cache at all) is
    slower and identical.

    The per-stage `cached`/`computed` split is LOGGED, because it is the only
    direct evidence that invalidating one stage recomputed one stage.

    Payloads this stage had to parse for itself are flushed before it returns, so an
    abort in a later stage does not discard them (#505).

    @brief Drive one cacheable per-file stage across the whole index.
    @version 3
    """
    parser_cache: dict = {}
    results: list[tuple[int, Any]] = []
    tally = HarvestTally()
    all_paths = conn.execute("SELECT rowid, name FROM path").fetchall()
    with make_progress(known_total=True) as progress:
        task = progress.add_task(harvester.label, total=len(all_paths))
        for path_rowid, rel_path in all_paths:
            progress.advance(task)
            payload = _harvest_one_file(
                rel_path,
                repo_root / rel_path,
                harvester,
                parser_cache,
                ts_classes,
                cache,
                tally,
            )
            if payload is not None:
                results.append((path_rowid, payload))
    ## Whatever THIS stage had to parse for itself is banked before the next one starts (#505).
    ## Normally near-free: since the shared pass most payloads are already cached and already
    ## flushed, so this commits nothing. It earns its place on the stages the shared pass does
    ## not cover, and on a build with no shared pass at all (`--no-index-cache` aside).
    if cache is not None:
        cache.flush()
    logger.info(
        "harvest %s: %d payload(s) from cache, %d parsed here",
        harvester.stage,
        tally.cached,
        tally.computed,
    )
    return results


## @brief Content sha of one file, or None when it cannot take part in caching.
## @param rel_path Repo-relative path (selects the grammar).
## @param abs_path Absolute path to read.
## @param cache Live index cache.
## @return The file's content sha, or None to leave it to the per-stage driver.
## @version 1
## @dg_internal
def _shareable_sha(rel_path: str, abs_path: Path, cache: IndexCache) -> str | None:
    """None means "not shareable", for either of the two reasons the per-stage
    driver already skips on: the path is not a parseable source file, or its sha
    could not be computed. In the second case the stages will each parse it for
    themselves — the pre-gh#358 behaviour, which is slow and correct.

    @brief Sha for a file the shared pass can warm, else None.
    @version 1
    """
    if _ts_language_for(rel_path) is None or not abs_path.is_file():
        return None
    return cache.sha_for(rel_path, abs_path)


## @brief Warm every stage that has no payload yet for one file, from one parse.
## @param rel_path Repo-relative path.
## @param abs_path Absolute path to read.
## @param harvesters Every stage the build will run.
## @param parser_cache Per-language parser memo.
## @param ts_classes (Language, Parser) from tree_sitter.
## @param cache Live index cache.
## @param tally Mutated in place with the cached/computed/parsed counts.
## @version 1
## @dg_internal
def _shared_parse_one_file(
    rel_path: str,
    abs_path: Path,
    harvesters: list[Harvester],
    parser_cache: dict,
    ts_classes: tuple[Any, Any],
    cache: IndexCache,
    tally: HarvestTally,
) -> None:
    """The parse is CONDITIONAL on at least one stage missing, which is what keeps
    an incremental refresh cheap: a file every stage already has stays ten sqlite
    existence checks and no parse.

    `extract_has` rather than `extract_get` on purpose — the shared pass only needs
    to know whether a row exists, and decoding ten payloads it is not going to use
    would make a warm refresh pay for the optimization.

    @brief Parse one file at most once and warm each stage that needs it.
    @version 1
    """
    sha = _shareable_sha(rel_path, abs_path, cache)
    if sha is None:
        return
    pending = [
        h for h in harvesters if not cache.extract_has(sha, h.stage, h.stage_version, h.extra_key)
    ]
    tally.cached += len(harvesters) - len(pending)
    if not pending:
        return
    language_cls, parser_cls = ts_classes
    parsed = _ast_parse_one_file(rel_path, abs_path, parser_cache, parser_cls, language_cls)
    if parsed is None:
        return
    tally.parsed += 1
    for harvester in pending:
        _store_payload(cache, harvester, sha, harvester.harvest(parsed[0], parsed[1]))
        tally.computed += 1


## @brief Parse every indexed file ONCE, warming all eleven stages' cache rows.
## @param conn Open connection to the database being built.
## @param repo_root Repository root the indexed paths are relative to.
## @param harvesters Every per-file stage this build will run.
## @param ts_classes (Language, Parser) from tree_sitter.
## @param cache Live index cache; None disables the pass entirely.
## @return The tally of payloads cached/computed and files parsed.
## @version 2
## @req REQ-DDB-PIPE-003
def run_shared_parse(
    conn: sqlite3.Connection,
    repo_root: Path,
    harvesters: list[Harvester],
    ts_classes: tuple[Any, Any],
    cache: IndexCache | None = None,
) -> HarvestTally:
    """gh#358. Nothing here EMITS: it only fills the per-stage cache rows the
    stages are about to read, so stage ordering — `ast_symbols` before every
    endpoint-resolving layer, `prune_fabricated_self_edges` inside call_edges,
    callback_edges applying its `PreprocessorConfig` after its own harvest — is
    untouched and stays the stages' business. That is why one pass can serve all
    ten despite an ordering constraint that forbids merging their EMITS:
    `Harvester.harvest(tree, src_bytes)` reads only the file, and payloads are
    rowid-free by contract.

    With no cache (`--no-index-cache`) there is nowhere to put the payloads, so
    this no-ops and every stage parses for itself exactly as it did before —
    slower, identical output.

    Payload rows are flushed every `_FLUSH_EVERY` files and once more at the end, so a
    build killed part-way through keeps what it has already parsed (#505).

    @brief One parse per file, feeding every stage's own cache row.
    @version 2
    """
    if cache is None or not harvesters:
        logger.info("shared ast parse: skipped (no index cache or no per-file stages)")
        return HarvestTally()
    parser_cache: dict = {}
    tally = HarvestTally()
    all_paths = conn.execute("SELECT rowid, name FROM path").fetchall()
    with make_progress(known_total=True) as progress:
        task = progress.add_task("shared ast parse", total=len(all_paths))
        for done, (_path_rowid, rel_path) in enumerate(all_paths, start=1):
            progress.advance(task)
            _shared_parse_one_file(
                rel_path,
                repo_root / rel_path,
                harvesters,
                parser_cache,
                ts_classes,
                cache,
                tally,
            )
            ## FLUSHED PART-WAY THROUGH, not merely at the end, and on a large target that is
            ## the whole value. This pass is the single longest stage there — a kill fifteen
            ## minutes into a twenty-minute parse banked NOTHING when the only flush was after
            ## the loop, which is the shape that made a big corpus unbuildable no matter how
            ## many times it was retried.
            if done % _FLUSH_EVERY == 0 and cache is not None:
                cache.flush()
    ## The tail the periodic flush above did not reach. `flush` persists payload rows only; the
    ## "this tree was indexed" claim stays with `commit`, after the swap.
    cache.flush()
    logger.info(
        "shared ast parse: %d file(s) parsed once for %d stage payload(s); "
        "%d payload(s) already cached across %d stage(s)",
        tally.parsed,
        tally.computed,
        tally.cached,
        len(harvesters),
    )
    return tally
