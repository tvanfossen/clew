# SPDX-License-Identifier: MIT
"""The shared tree-sitter walk behind both detectors — corpus, no policy.

Two rules here are load-bearing and neither is obvious.

**Never a regex over source text.** Two independent implementations of the same
written detector spec disagreed by 14-36% on how many accessor call sites the
real codebases hold, because a text regex counts occurrences inside comments,
string literals and `#if 0` blocks. Call sites come from `call_expression`
nodes and nothing else.

**Two corpora, not one.** RESOLUTION runs over the WHOLE repo tree, because an
out-of-scope macro is routinely an intermediate link in a spawn chain (the IoT
lib's `SYSTEM_TASKCREATE` lives in a submodule). PROPOSAL runs only over
definitions INSIDE the derived index scope, because a wrapper clew cannot
attribute call sites for is a wrapper it must not declare. Every record
therefore carries `in_scope`, and the detectors — not this module — decide what
that means.

The census is a SECOND pass, byte-prefiltered to files that mention a candidate
name. It cannot merge into the first pass because its watch set is the first
pass's output, and keeping every call site of a 4.6k-file tree in memory to
avoid re-parsing a few dozen files is the wrong trade.

@brief Repo-wide tree-sitter corpus: definitions, forwarding calls, accessor sites.
@version 1
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..harvest import _ast_parse_one_file, _ts_language_for
from ..scope import DerivedScope
from .astdefs import (
    CALLEE_TYPES,
    DEF_TYPES,
    FuncDef,
    callee_name,
    definition_record,
    enclosing_definition,
    walk,
)

## Directories never walked. Dot-directories are pruned separately. Mirrors
## `scope._SKIP_DIR_NAMES` — a traversal cost guard, not a scope decision.
_PRUNE_DIRS = frozenset({"__pycache__", "node_modules"})

## Runaway guard on the repo-wide corpus. The largest real codebase enumerates
## ~4.6k C/C++ files; a tree an order of magnitude bigger is a mount point or a
## monorepo, and silently spending minutes on it is worse than saying so.
MAX_CORPUS_FILES = 20000


## @brief One accessor-shaped call site (key-in-name convention candidate).
## @version 1
@dataclass(frozen=True)
class AccessorSite:
    """Only the arity is kept, not the argument text: the arity gate is the
    discriminator (a name-keyed setter takes exactly one argument, a getter
    none), and retaining argument text for every accessor call in a large repo
    costs hundreds of megabytes for no gain.

    @brief An accessor-shaped call site: callee, arity, location, scope.
    @version 1
    """

    rel_path: str
    line: int
    callee: str
    argc: int
    in_scope: bool


## @brief One call site of a watched callee, with its enclosing context.
## @version 1
@dataclass(frozen=True)
class CallSite:
    """Collected in the second (watch-set) pass, once candidate names are known.
    `enclosing_params` is what separates a CONCRETE spawn site (a real entry
    function is named) from a FORWARDING one (the enclosing definition is itself
    a wrapper) — the census the thread detector gates on.

    @brief A call site of a watched callee plus its enclosing definition.
    @version 1
    """

    rel_path: str
    line: int
    callee: str
    arg_texts: tuple[str, ...]
    enclosing_fn: str
    enclosing_params: tuple[str, ...]
    in_scope: bool


## @brief The whole-repo corpus one scan produced.
## @version 1
@dataclass
class Corpus:
    """A mutable accumulator by design — it is filled file by file and then read
    only. Frozen would buy nothing and cost a copy per file.

    @brief Definitions by name, accessor sites, and scan counters.
    @version 1
    """

    defs: dict[str, list[FuncDef]] = field(default_factory=dict)
    accessor_sites: list[AccessorSite] = field(default_factory=list)
    files_parsed: int = 0
    files_in_scope: int = 0
    truncated: bool = False


## @brief Every C/C++ source file under a repo root, in sorted order.
## @param repo_root Root to walk.
## @return Absolute paths of files a tree-sitter grammar exists for.
## @version 1
## @req REQ-DDB-CONFIG-001
def repo_source_files(repo_root: Path) -> tuple[Path, ...]:
    """Walk the tree once, pruning dot-directories and cache/vendor directories,
    and keep only paths `harvest._ts_language_for` recognises — the exact filter
    the pipeline's own per-file stages use, so the corpus can never be wider
    than what the pipeline could parse.

    @brief Enumerate the repo's parseable source files.
    @version 1
    """
    found: list[Path] = []
    stack = [repo_root]
    while stack:
        for entry in _scandir(stack.pop()):
            if entry.is_dir(follow_symlinks=False):
                if not entry.name.startswith(".") and entry.name not in _PRUNE_DIRS:
                    stack.append(Path(entry.path))
            elif _ts_language_for(entry.name) is not None:
                found.append(Path(entry.path))
    return tuple(sorted(found))


## The grammars whose node shapes `astdefs` reads. `_ts_language_for` also routes
## Python now, and a Python `function_definition` has a `name`/`parameters` shape
## rather than C's `declarator` chain — so those files parse, contribute nothing,
## and would otherwise make an untouched Python codebase look like a MEASURED empty
## C repo. Named here so the detectors can say which of the two it is.
_AST_GRAMMARS = frozenset({"tree_sitter_c", "tree_sitter_cpp"})


## @brief How many in-scope files a grammar the AST detectors understand handles.
## @param files Files enumerated by repo_source_files.
## @param in_scope Scope-membership predicate from scope_membership.
## @return Count of in-scope files with a C/C++ grammar.
## @version 1
## @req REQ-DDB-CONFIG-001
def ast_readable_in_scope(files: tuple[Path, ...], in_scope: Any) -> int:
    """Keyed on the grammar module `_ts_language_for` chooses, not on a duplicated
    extension list, so widening that router (as the Python layer did) cannot
    silently widen what these detectors claim to have measured.

    @brief Count the in-scope files the C/C++ detectors can actually read.
    @version 1
    """
    return sum(
        1
        for path in files
        if getattr(_ts_language_for(path.name), "__name__", "") in _AST_GRAMMARS
        and bool(in_scope(path))
    )


## @brief Directory entries, or an empty list when the directory is unreadable.
## @param directory Directory to list.
## @return The scandir entries, sorted by name.
## @version 1
## @dg_internal
def _scandir(directory: Path) -> list[os.DirEntry]:
    """@brief List one directory, tolerating permission errors."""
    try:
        return sorted(os.scandir(directory), key=lambda e: e.name)
    except OSError:
        return []


## @brief Build the "is this path inside the derived index scope?" predicate.
## @param scope The derived index scope.
## @return A callable taking an absolute path and returning True when in scope.
## @version 1
## @req REQ-DDB-CONFIG-001
def scope_membership(scope: DerivedScope) -> Any:
    """The scope's roots are absolute paths (a directory OR a single file — the
    guard derivation emits both) and its excludes prune subtrees beneath them.

    @brief Make a scope-membership predicate for absolute paths.
    @version 1
    """
    roots = [Path(r) for r in scope.roots]
    excludes = [Path(e) for e in scope.excludes]

    ## @brief Whether one absolute path lies inside the derived scope.
    ## @param path Absolute path to test.
    ## @return True when the path is under a root and under no exclude.
    ## @version 1
    def inside(path: Path) -> bool:
        """@brief Test one path against the derived roots and excludes."""
        if any(path == ex or ex in path.parents for ex in excludes):
            return False
        return any(path == root or root in path.parents for root in roots)

    return inside


## @brief Scan the whole repo tree for definitions and accessor-shaped calls.
## @param repo_root Repo root the paths are relative to.
## @param files Files to parse (from repo_source_files).
## @param in_scope Scope-membership predicate from scope_membership.
## @param ts_classes (Language, Parser) from tree_sitter.
## @param accessor_split Callable(name) -> None when the name is not accessor-shaped.
## @return The assembled Corpus.
## @version 1
## @req REQ-DDB-CONFIG-001
def scan_repo(
    repo_root: Path,
    files: tuple[Path, ...],
    in_scope: Any,
    ts_classes: tuple[Any, Any],
    accessor_split: Any,
) -> Corpus:
    """One pass over every file collecting the two compact things the detectors
    need: definitions with their parameter-forwarding calls, and accessor-shaped
    call sites. Both are recorded repo-wide and tagged `in_scope`, per the
    two-corpora rule in the module docstring.

    @brief Build the repo-wide corpus in a single parse pass.
    @version 1
    """
    corpus = Corpus(truncated=len(files) > MAX_CORPUS_FILES)
    parser_cache: dict = {}
    language_cls, parser_cls = ts_classes
    for path in files[:MAX_CORPUS_FILES]:
        rel = relative_to(path, repo_root)
        parsed = _ast_parse_one_file(rel, path, parser_cache, parser_cls, language_cls)
        if parsed is None:
            continue
        corpus.files_parsed += 1
        scoped = bool(in_scope(path))
        corpus.files_in_scope += 1 if scoped else 0
        _absorb_file(corpus, parsed, rel, scoped, accessor_split, ts_classes)
    return corpus


## @brief Fold one parsed file's definitions and accessor sites into the corpus.
## @param corpus Corpus being built (mutated).
## @param parsed (tree, src_bytes) for the file.
## @param rel Repo-relative path.
## @param scoped Whether the file is inside the derived index scope.
## @param accessor_split Accessor-shape predicate.
## @param ts_classes (Language, Parser) from tree_sitter.
## @version 1
## @dg_internal
def _absorb_file(
    corpus: Corpus,
    parsed: tuple[Any, bytes],
    rel: str,
    scoped: bool,
    accessor_split: Any,
    ts_classes: tuple[Any, Any],
) -> None:
    """@brief Record one file's definitions and accessor call sites."""
    tree, src = parsed
    for node in walk(tree.root_node):
        if node.type in DEF_TYPES:
            fdef = definition_record(node, src, rel, scoped, ts_classes)
            if fdef is not None:
                corpus.defs.setdefault(fdef.name, []).append(fdef)
        elif node.type == "call_expression":
            site = _accessor_site(node, src, rel, scoped, accessor_split)
            if site is not None:
                corpus.accessor_sites.append(site)


## @brief One accessor-shaped call site, or None when the callee is not one.
## @param node A call_expression node.
## @param src Raw file bytes.
## @param rel Repo-relative path.
## @param scoped Whether the file is in the index scope.
## @param accessor_split Accessor-shape predicate.
## @return An AccessorSite, or None.
## @version 1
## @dg_internal
def _accessor_site(
    node: Any, src: bytes, rel: str, scoped: bool, accessor_split: Any
) -> AccessorSite | None:
    """@brief Record a call site whose callee name is accessor-shaped."""
    name = callee_name(node, src)
    if not name or accessor_split(name) is None:
        return None
    args = node.child_by_field_name("arguments")
    argc = len(args.named_children) if args is not None else 0
    return AccessorSite(rel, node.start_point[0] + 1, name, argc, scoped)


## @brief Second pass: every call site of a watched callee, repo-wide.
## @param repo_root Repo root the paths are relative to.
## @param files Files to consider (from repo_source_files).
## @param in_scope Scope-membership predicate.
## @param ts_classes (Language, Parser) from tree_sitter.
## @param watch Callee names to collect sites for.
## @return Every matching call site, in file order.
## @version 1
## @req REQ-DDB-CONFIG-001
def census_call_sites(
    repo_root: Path,
    files: tuple[Path, ...],
    in_scope: Any,
    ts_classes: tuple[Any, Any],
    watch: frozenset[str],
) -> list[CallSite]:
    """Byte-prefiltered: a file that does not literally contain a watched name
    cannot hold a call to it, so it is never parsed. That turns the second pass
    from "parse the tree again" into "parse the handful of files that mention
    the candidates".

    @brief Collect repo-wide call sites for a small set of callee names.
    @version 1
    """
    if not watch:
        return []
    needles = [name.encode("utf-8") for name in watch]
    parser_cache: dict = {}
    language_cls, parser_cls = ts_classes
    sites: list[CallSite] = []
    for path in files[:MAX_CORPUS_FILES]:
        raw = _read_bytes(path)
        if raw is None or not any(needle in raw for needle in needles):
            continue
        rel = relative_to(path, repo_root)
        parsed = _ast_parse_one_file(rel, path, parser_cache, parser_cls, language_cls)
        if parsed is not None:
            _collect_watched(sites, parsed, rel, bool(in_scope(path)), watch)
    return sites


## @brief A file's bytes, or None when it cannot be read.
## @param path File to read.
## @return The raw bytes, or None.
## @version 1
## @dg_internal
def _read_bytes(path: Path) -> bytes | None:
    """@brief Read a file for the census prefilter, tolerating I/O errors."""
    try:
        return path.read_bytes()
    except OSError:
        return None


## @brief Collect one file's call sites for the watched callee names.
## @param sites Accumulator (mutated).
## @param parsed (tree, src_bytes) for the file.
## @param rel Repo-relative path.
## @param scoped Whether the file is inside the index scope.
## @param watch Callee names of interest.
## @version 1
## @dg_internal
def _collect_watched(
    sites: list[CallSite], parsed: tuple[Any, bytes], rel: str, scoped: bool, watch: frozenset[str]
) -> None:
    """@brief Record every call to a watched callee in one parsed file."""
    tree, src = parsed
    for node in walk(tree.root_node):
        if node.type != "call_expression":
            continue
        name = callee_name(node, src)
        if name not in watch:
            continue
        sites.append(_call_site(node, src, rel, scoped, name))


## @brief Build a CallSite record for one matched call node.
## @param node The call_expression node.
## @param src Raw file bytes.
## @param rel Repo-relative path.
## @param scoped Whether the file is inside the index scope.
## @param name The matched callee name.
## @return The assembled CallSite.
## @version 1
## @dg_internal
def _call_site(node: Any, src: bytes, rel: str, scoped: bool, name: str) -> CallSite:
    """@brief Assemble one watched call site with its enclosing definition."""
    args = node.child_by_field_name("arguments")
    texts = tuple(
        src[a.start_byte : a.end_byte].decode("utf-8", errors="replace")
        for a in (args.named_children if args is not None else [])
    )
    fn_name, params = enclosing_definition(node, src)
    return CallSite(rel, node.start_point[0] + 1, name, texts, fn_name, params, scoped)


## @brief Repo-root-relative POSIX path for an absolute path under the root.
## @param path Absolute path.
## @param repo_root Repo root.
## @return The relative path, or the absolute string when it is outside.
## @version 1
## @req REQ-DDB-CONFIG-001
def relative_to(path: Path, repo_root: Path) -> str:
    """@brief Key a scanned path the way doxygen's `path` table does."""
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return str(path)


__all__ = [
    "CALLEE_TYPES",
    "MAX_CORPUS_FILES",
    "AccessorSite",
    "CallSite",
    "Corpus",
    "FuncDef",
    "ast_readable_in_scope",
    "census_call_sites",
    "relative_to",
    "repo_source_files",
    "scan_repo",
    "scope_membership",
]
