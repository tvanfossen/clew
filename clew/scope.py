# SPDX-License-Identifier: MIT
"""Resolve the index scope: a declaration, else the whole repository.

TWO tiers, and the Doxyfile is no longer one of them (gh#333). The first is the
repo's own `index_scope:` — the only tier that is a DECISION about the index. The
second is the repository itself, less what git ignores, which is what every repo
gets for saying nothing.

A DOXYFILE `INPUT` IS A DOCUMENTATION TARGET, NOT A REASONING BOUNDARY, and reading
it as one inverted the tool: a repo shipping no Doxyfile got whole-repo scope while
a repo shipping one got its published-API subset, so a repo was PUNISHED for
documenting itself. Measured on Mbed-TLS/mbedtls, whose `doxygen/mbedtls.doxyfile`
sets `INPUT = ../include` and `FILE_PATTERNS = *.h`: honouring it indexes 1,571
header declarations and zero of the 108 `library/*.c` implementations. The repo's
own Doxyfile is still USED — it carries ALIASES, PREDEFINED and filters synthesis
cannot reconstruct — but its INPUT is replaced.

The doxygen-guard hook's `files:` pattern is deliberately not a tier either. That
pattern is the GATE's boundary: it answers what must be DOCUMENTED, not what should
be REASONABLE-ABOUT.

NESTED GIT TREES ARE INDEXED, NOT EXCLUDED (gh#333/gh#335). A submodule used to be
walked for, found, and cut out, on the argument that two codebases in one index
cannot be told apart in a search result. The premise was right and the remedy was
backwards: entropic wraps llama.cpp, and a `chain_trace` that stops at the submodule
boundary answers "this call leaves the repo" when it could answer what the call
does. They are told apart by being TAGGED instead — see `external.py`, which reuses
the same walk this module already ran and threw away. `nested_repo_roots` is that
walk, made public.

WHAT REMAINS EXCLUDED IS WHAT GIT IGNORES, on BOTH sides of a submodule boundary.
`git ls-files --ignored` is opaque through a submodule, so the nested repo's own
ignores are collected separately; without that, entropic's vendored CMake
FetchContent output (`examples/*/build/_deps/**`) walks straight back in.

Nothing here is repo-specific. Every tier reads a declaration or the tree itself.

@brief Index scope resolution: declaration → whole repo, nested trees included.
@version 3
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ._common import logger
from .gitenv import git_env
from .precommit import discover_guard_config

# Directories never worth walking: caches/vendor dirs that no repo declares as
# in-scope source. Dot-directories are pruned separately. This is a traversal
# cost guard, NOT a scope decision.
_SKIP_DIR_NAMES = frozenset({"__pycache__", "node_modules"})

# Depth at which the walk stops descending. Deeper directories are taken
# wholesale (and reported) rather than scanned; 16 is far below any real
# source layout, so this is a runaway guard, not a policy.
_MAX_DEPTH = 16

## Directories the last derivation stopped descending into, absolute, in walk order.
##
## RECORDED BECAUSE "REPORTED" MEANT "LOGGED", AND A LOG IS GONE BY QUERY TIME. Hitting the
## limit is not a neutral event: below that point nothing is pruned and nothing is checked for
## nested trees, so the walk admits whatever is there — which on a deeply nested vendored
## dependency is tens of thousands of files nobody asked for. The build said so at WARNING and
## then threw it away, so the index could not answer why its corpus was the size it was. This is
## the same "persisting what the pipeline already computed" shape as scope provenance itself.
##
## MODULE STATE, RESET PER DERIVATION by `derive_scope`, which is the single entry point. Read
## through `depth_limited_paths()` immediately after a derivation; anything else is reading
## somebody else's walk.
_DEPTH_LIMITED: list[Path] = []


## The sub-index holding everything the repository itself owns — every file not inside a nested
## git tree. Named rather than left implicit because it is addressed like any other sub-index
## (`<repo>#first-party`) and appears in slugs, logs and replies.
FIRST_PARTY_INDEX = "first-party"


## @brief One index of a repository: a name, its roots, and what it leaves out.
## @version 1
@dataclass(frozen=True)
class SubIndex:
    """A repository split into several indexes, so the parts that never change are built once.

    THE SPLIT IS ALONG GIT TREES, WHICH IS WHY IT PAYS. A vendored dependency is pinned by its
    gitlink, so its index is immutable — built once and never rebuilt — while the recurring loop
    touches only first-party code. Measured on a target vendoring llama.cpp: 592 files and 13.9 s
    for first-party against 3,521 files and 69.0 s for the whole repository, losing 13 of 4,968
    first-party-internal call edges (0.26%).

    A git tree is also a natural SEAM, which the rejected chunking attempt was not: 82.5% of that
    target's call graph never leaves the vendored tree, and only 2.6% crosses the boundary at all,
    against the 18% of edges arbitrary directory chunks destroyed.

    @brief One named index of a repository.
    @version 1
    """

    name: str
    roots: tuple[Path, ...]
    excludes: tuple[Path, ...]


## @brief Name a nested tree by its repo-relative path, safe as a directory component.
## @param nested Absolute path of the nested tree.
## @param repo_root Absolute repository root.
## @return A unique, stable, path-safe name.
## @version 1
## @dg_internal
def _sub_index_name(nested: Path, repo_root: Path) -> str:
    """DERIVED FROM THE RELATIVE PATH, NOT THE BASENAME, because two vendored trees can share a
    basename — `a/dep` and `b/dep` — and colliding names would land both on one database, which
    is the wrong-index failure this project has recorded as its most expensive.

    Stability matters as much as uniqueness: nothing persists a mapping from name to database, so
    this derivation IS the mapping, exactly as the path digest is for a whole-repo slug.

    @brief Name one nested tree.
    @return The sub-index name.
    @version 1
    """
    relative = nested.relative_to(repo_root).as_posix()
    return "-".join(part for part in relative.split("/") if part)


## @brief Whether a path is one of, or inside, any of the given roots.
## @param path The path to test, already resolved.
## @param roots Resolved paths to test against.
## @return True when `path` is a root or lies under one.
## @version 1
## @dg_internal
def _under_any(path: Path, roots: set[Path]) -> bool:
    """EQUALITY AS WELL AS CONTAINMENT. An exclusion names the directory itself, so testing only
    `parents` would keep a nested tree that IS the excluded path — and `build/_deps/catch2-src`
    excluded exactly is the shape that occurs.

    @brief Test containment against a set of roots.
    @return Whether the path falls under any root.
    @version 1
    """
    return path in roots or any(parent in roots for parent in path.parents)


## @brief Every nested git tree under one root, at ANY depth.
## @param under Directory to walk (a repo root, or a previously found nested tree).
## @param ignored Resolved paths to filter out at every level (gitignored clones, etc.).
## @return Resolved paths of every nested tree found, at any depth, unsorted.
## @version 1
## @dg_internal
def _nested_trees_recursive(under: Path, ignored: set[Path]) -> list[Path]:
    """`nested_repo_roots` ITSELF ALREADY STOPS DESCENT at the first `.git` it finds — by
    design, so a submodule's OWN internals are not walked for the boundary that owns them.
    That is exactly right for ONE level and exactly wrong for splitting: it is also why a
    vendored tree's OWN vendored trees (b12-slam's boost/opencv/pcl, libBissellIoT's own
    curl/mbedtls/paho) were swallowed whole into their parent's sub-index instead of getting
    their own. Recursing HERE — calling `nested_repo_roots` again from INSIDE each tree it
    finds — is what gives each of those its own identity, without changing what any single
    call does.

    `ignored` IS EXTENDED PER LEVEL, not reused unchanged. A tree's own `.gitignore` is
    invisible to a walk rooted above it (`git ls-files` stops at every boundary, the same
    reason `whole_repo_scope` asks each nested tree for its own ignores rather than the
    parent's), so a CMake `_deps`-style throwaway clone nested two levels down needs the
    SAME filtering a one-level-down one already gets — extending the set per level is what
    makes that consistent at any depth rather than only the first.

    BOUNDED BY THE FILESYSTEM, NOT BY A COUNTER. Each call's own walk is capped by
    `_MAX_DEPTH` as always; recursion terminates because real nesting bottoms out at a
    finite number of actual git-tree boundaries, which a vendored dependency graph never
    has many of even when it has more than one.

    @brief Recursively find nested git trees at every depth under one root.
    @return Every nested tree found, unsorted, at any depth.
    @version 1
    """
    direct = sorted(
        p for p in {q.resolve() for q in nested_repo_roots(under)} if not _under_any(p, ignored)
    )
    found = list(direct)
    for tree in direct:
        deeper_ignored = ignored | {p.resolve() for p in _gitignored_paths(tree)}
        found.extend(_nested_trees_recursive(tree, deeper_ignored))
    return found


## @brief The closest containing root for one nested tree, among a repo's own split.
## @param tree A nested tree found somewhere under `root`.
## @param root The repository root.
## @param all_nested Every nested tree found anywhere in the repo (any depth).
## @return The nearest ancestor — `root` itself, or the closest containing nested tree.
## @version 1
## @dg_internal
def _direct_parent(tree: Path, root: Path, all_nested: list[Path]) -> Path:
    """A TREE'S OWN SUB-INDEX MUST EXCLUDE ITS DIRECT CHILDREN ONLY, mirroring exactly what
    first-party already does relative to depth 1: `roots=[tree]` bounds a build's INPUT to
    everything under `tree`, so a GRANDCHILD nested tree is still inside that boundary and
    still needs an explicit exclude to stay out of it — this is what supplies that exclude
    to the right level, rather than every nested tree's exclude list naming every deeper
    descendant regardless of which parent actually contains it directly.

    @brief Find which root (the repo, or another nested tree) directly contains `tree`.
    @return The nearest containing ancestor.
    @version 1
    """
    ancestors = [c for c in (root, *all_nested) if c != tree and c in tree.parents]
    return max(ancestors, key=lambda p: len(p.parts))


## @brief Split a repository into first-party and per-nested-tree indexes, at any depth.
## @param repo_root The repository root.
## @return The sub-indexes, or an empty list when the repo holds no nested trees.
## @version 3
## @req REQ-DDB-INDEX-002
def derive_sub_indexes(repo_root: Path) -> list[SubIndex]:
    """EMPTY MEANS "DO NOT SPLIT", and that is the compatibility contract. A repository with
    nothing vendored must keep building to one index under the slug it already has — splitting it
    would allocate a new slug and strand the index on disk, whose symptom is "no database has been
    built" against a perfectly good one.

    REUSES `nested_repo_roots`, which the pipeline already runs on every build and which handles
    BOTH on-disk shapes of a nested repository: a clone's `.git` directory and a submodule's
    `gitdir:` pointer FILE. That distinction is not academic — a detector seeing only directories
    finds nested clones and silently skips every submodule, which is the case this split exists
    for.

    N LEVELS DEEP, NOT ONE. Field-reported: a vendored dependency that itself vendors several
    more (a 1.2GB tree carrying boost, opencv, pcl and six others as its own submodules) was
    getting ONE sub-index for the whole thing, dominated entirely by code none of it wrote.
    Every nested tree found anywhere in the repository — at any depth — gets its own name and
    its own sub-index; each one's `excludes` names exactly its own direct children, the same
    relationship first-party already has to depth 1, so building it does not silently swallow
    what belongs one level further down.

    @brief Derive the sub-index split from nested git trees, at any depth.
    @return The split, or [] to build the repository whole.
    @version 3
    """
    root = Path(repo_root).expanduser().resolve()
    ## THE SPLIT USES THE BUILD'S OWN RULE, and skipping this cost a real target twenty minutes.
    ## `nested_repo_roots` walks the WHOLE tree, so it finds every git clone on disk — including
    ## CMake FetchContent output under `build/`, which is a genuine clone and pure throwaway.
    ## Driving a real repository produced sub-indexes named `build-coverage-_deps-catch2-src`,
    ## `build-dev-_deps-httplib-src` and six more, each being indexed in turn, while every
    ## fixture test passed.
    ##
    ## `whole_repo_scope` already computes what the build excludes — git-ignored paths, plus each
    ## nested tree's own ignores, which `git ls-files` cannot see through. Reusing it is what
    ## keeps the split and the build agreeing about what the repository contains; deriving a
    ## second rule here would leave the split free to index trees the build would never touch,
    ## and the split is the one nobody looks at.
    ignored = {p.resolve() for p in whole_repo_scope(root).excludes}
    nested = sorted(set(_nested_trees_recursive(root, ignored)))
    if not nested:
        return []
    ## EACH TREE EXCLUDES ONLY ITS OWN DIRECT CHILDREN, not every deeper descendant — a
    ## grandchild is already excluded from ITS OWN parent's build, which is the tree one level
    ## up from it, not from every ancestor above that.
    children_of: dict[Path, list[Path]] = {}
    for tree in nested:
        parent = _direct_parent(tree, root, nested)
        children_of.setdefault(parent, []).append(tree)
    first = SubIndex(
        name=FIRST_PARTY_INDEX, roots=(root,), excludes=tuple(children_of.get(root, []))
    )
    others = [
        SubIndex(
            name=_sub_index_name(tree, root),
            roots=(tree,),
            excludes=tuple(children_of.get(tree, [])),
        )
        for tree in nested
    ]
    return [first] + others


## @brief Directories the last derivation refused to descend past.
## @return Absolute paths, in walk order.
## @version 1
## @utility
def depth_limited_paths() -> list[Path]:
    """A COPY, so a caller cannot mutate the record it is reading.

    @brief Report where the walk hit its depth limit.
    @return The recorded directories.
    @version 1
    """
    return list(_DEPTH_LIMITED)


# Scope provenance markers reported to the caller and the log.
## HISTORICAL SINCE gh#333, and kept for exactly that reason: no build produces it
## any more, but an index built before gh#333 has it STAMPED in `build_meta`, and a
## reader that does not know the token cannot tell "this index took the Doxyfile's
## documentation subset" from "this value is corrupt". Deleting a vocabulary entry
## does not delete the data already written under it.
SOURCE_DOXYFILE = "doxyfile"
## The repo itself, reached whenever nothing narrower is DECLARED — which since
## gh#333 is the default rather than the last resort. It is the WIDEST scope, so it
## is also the one certain to contain any nested git tree; those are indexed and
## tagged external rather than cut out.
SOURCE_WHOLE_REPO = "whole-repo"
## An `index_scope:` section in the repo's own `.clew.yaml`, or in the
## `x-clew` passthrough of its doxygen-guard config. The only tier that states
## a knowledge boundary rather than borrowing one stated for another purpose.
SOURCE_DECLARED = "clew-declaration"

## Declaration section naming the index roots/excludes.
INDEX_SCOPE_SECTION = "index_scope"

## The keys an `index_scope:` block may carry. Spelled once so the validator below and the
## message it emits cannot disagree about what is accepted.
_INDEX_SCOPE_KEYS = frozenset({"roots", "excludes"})


## @brief A declaration that WAS present and could not be used, carrying why.
## @version 1
## @dg_internal
class _Rejected(str):
    """A `str` subclass so it is the reason itself, not a wrapper something must unpack.

    THE POINT IS THAT IT IS TRUTHY AND DISTINGUISHABLE. `_declared_index_scope` previously
    returned None for both "no section" and "a section I could not use", and `derive_scope`'s
    `A or B` collapsed them into the same whole-repo reason. A truthy sentinel keeps the
    existing `or` idiom working for the genuinely-absent case while letting the caller tell the
    two apart with one isinstance check.
    """


# `--scope` choices: the Doxyfile's own INPUT, or the repo's own declarations.
SCOPE_DOXYFILE = "doxyfile"
SCOPE_FROM_GUARD = "from-guard"


## @brief Derived index scope plus the provenance of that decision.
## @version 3
@dataclass(frozen=True)
class DerivedScope:
    """Absolute INPUT roots and EXCLUDE paths, the tier they came from, and a
    human-readable reason — so the build log can always say WHICH scope was used and
    WHY.

    Only a DECLARED scope carries roots that override a Doxyfile. The doxyfile tier
    carries a reason and nothing else, and the whole-repo tier carries the repository
    as its single root; both are what a repo gets by saying nothing, and `source`
    distinguishes them.

    @brief Result of scope resolution.
    @version 3
    """

    source: str
    reason: str
    roots: tuple[Path, ...] = ()
    excludes: tuple[Path, ...] = ()

    ## @brief Whether this scope should override the Doxyfile's INPUT.
    ## @return True when a declaration produced usable roots.
    ## @version 3
    ## @req REQ-DDB-CONFIG-001
    def is_derived(self) -> bool:
        """@brief Whether a declaration produced usable roots."""
        return self.source == SOURCE_DECLARED and bool(self.roots)


## @brief Whether a directory entry should be skipped outright by the walk.
## @param name Directory base name.
## @return True for dot-directories and known cache/vendor directories.
## @version 1
## @dg_internal
def _skip_dir(name: str) -> bool:
    """@brief Prune dot-directories and cache directories from the walk."""
    return name.startswith(".") or name in _SKIP_DIR_NAMES


## @brief How to declare an index scope, in this build's own spelling.
## @return A sentence naming both places a declaration may live.
## @version 3
## @req REQ-DDB-CONFIG-001
def _declaration_advice() -> str:
    """A fallback scope reports that the boundary was not chosen; without this it does
    not report the fix, and a diagnosis an owner cannot act on is half a diagnosis
    (gh#32's lesson about the skew report, one tier up).

    Spellings are imported rather than written out, so the advice cannot drift from the
    names the loader actually accepts — the failure `test_declaration.py` pins for
    `index_scope` itself. Imported lazily because `declaration` reads a declaration and
    `scope` interprets one; the module-level cycle is what `_declared_index_scope`
    already avoids the same way.

    @brief Name the declarations that would narrow a fallback scope.
    @return The advice sentence.
    @version 3
    """
    from .declaration import (
        DECLARATION_NAME,
        GUARD_CONFIG_NAME,
        PASSTHROUGH_TOOL,
    )

    return (
        f"Declare `x-{PASSTHROUGH_TOOL}: {INDEX_SCOPE_SECTION}:` in {GUARD_CONFIG_NAME}, "
        f"or an `{INDEX_SCOPE_SECTION}:` in {DECLARATION_NAME}, to let the two differ."
    )


## @brief Whether the repo's own index_scope would be REJECTED, without the fallback.
## @param repo_root Repo root to check.
## @param guard_config Explicit guard-config path overriding discovery, or None.
## @param stated A tier-1 caller's own stated index_scope, or None to read the declared one.
## @return The rejection reason, or None when the declaration is usable or absent entirely.
## @version 1
## @req REQ-DDB-CONFIG-001
def declared_scope_rejection(
    repo_root: Path, guard_config: Path | str | None = None, stated: dict | None = None
) -> str | None:
    """`derive_scope` ABSORBS a rejected declaration into the whole-repo tier — a
    deliberate choice for every INTERNAL pipeline caller, which must always get back a
    usable scope rather than an exception. That absorption is exactly what let an
    excludes-only `.clew.yaml` cost B12_single_rgb a 900s doxygen timeout under a
    vendored tree its own declaration was trying to keep out: the WARNING logged the
    contradiction, and the build proceeded into the widest possible scope anyway.

    This is the SEPARATE, BUILD-TIME check a caller who can still refuse (the MCP refresh
    path, the CLI) runs before committing to a scope — the same relationship
    `stale_code_refusal` has to the build it guards: a guard function, not a change to
    what the guarded thing itself does. `derive_scope`'s own contract is untouched, so
    every existing caller of THAT function keeps its current behaviour exactly.

    @brief Report whether the declared or stated index_scope would be rejected.
    @return The rejection reason, or None.
    @version 1
    """
    declared = _declared_index_scope(Path(repo_root).expanduser().resolve(), guard_config, stated)
    return str(declared) if isinstance(declared, _Rejected) else None


## @brief Resolve the index scope: a declared index_scope, else the whole repository.
## @param repo_root Repo root to resolve scope for.
## @param guard_config Explicit guard-config path overriding discovery, or None.
## @return DerivedScope; the whole-repo tier when no usable declaration exists.
## @version 9
## @req REQ-DDB-CONFIG-001
def derive_scope(
    repo_root: Path, guard_config: Path | str | None = None, stated: dict | None = None
) -> DerivedScope:
    """Read the declaration and hand back its roots. Every failure mode — no config,
    no `index_scope:` section, no declared root that exists — falls through to
    `whole_repo_scope`, which carries the REASON, so the caller can log which scope
    was used and why. Nothing is ever silently guessed.

    THE DOXYFILE FALLBACK IS GONE (gh#333). It used to sit here and name no roots at
    all, which handed the indexed tree to the Doxyfile's own INPUT — a documentation
    target standing in for a reasoning boundary. `_doxyfile_fallback`'s one surviving
    job, saying WHERE a declaration was looked for, is now a clause inside the
    whole-repo reason.

    NO CONTAINMENT PASS. Every scope this module handed out used to run through
    `_with_nested_repos_contained`, which cut nested git trees out of it. They are
    now indexed and tagged instead (`external.py`), so the choke point was removed
    rather than bypassed — a containment call left in place with its callers removed
    is a safety property that reads as enforced and is not.

    @brief Resolve INPUT roots from the repo's own index-scope declaration.
    @return The declared scope, or the whole-repo tier.
    @version 9
    """
    ## CLEARED HERE BECAUSE THIS IS THE SINGLE ENTRY POINT, so `depth_limited_paths()` after a
    ## derivation describes THAT derivation and not an accumulation across several. The build
    ## derives more than once — `_scope_provenance` re-derives on the whole-repo tier — and a
    ## record that grew across them would report the same directory two or three times and read
    ## as a wider problem than exists.
    _DEPTH_LIMITED.clear()
    root = Path(repo_root).expanduser().resolve()
    declared = _declared_index_scope(root, guard_config, stated)
    if isinstance(declared, _Rejected):
        ## SAID OUT LOUD, not only returned. The contradiction gh#5 reports is between two LOG
        ## lines, so the correction has to reach the log too — a reason carried only in the
        ## payload leaves the WARNING still claiming absence.
        logger.warning("index_scope: %s", declared)
        return whole_repo_scope(root, guard_config, rejected=str(declared))
    return declared or whole_repo_scope(root, guard_config)


## @brief The whole repository as one INPUT root, less only what git ignores.
## @param repo_root Repo root to index in full.
## @param guard_config Explicit guard-config path overriding discovery, or None.
## @return A DerivedScope rooted at the repo, nested git trees INCLUDED.
## @version 2
## @req REQ-DDB-CONFIG-001
def whole_repo_scope(
    repo_root: Path, guard_config: Path | str | None = None, rejected: str = ""
) -> DerivedScope:
    """THE DEFAULT TIER since gh#333, not the last resort: reached whenever a repo
    declares no `index_scope:`, whether or not it ships a Doxyfile.

    Its single root is the whole repository, so a foreign clone parked anywhere
    inside is inside it BY CONSTRUCTION — and since gh#333 that is the intent rather
    than the hazard it used to be. entropic wraps llama.cpp; a `chain_trace` that
    stopped at the submodule boundary said "this call leaves the repo" when it could
    have said what the call does. `external.py` tags those rows so the two codebases
    are still told apart in an answer.

    The subtractions are what the repo has already said about itself — the paths git
    ignores, on BOTH sides of every submodule boundary — plus the dot and cache
    directories no repo restates. The doxygen-guard gate is NOT read here: the gate
    answers what must be DOCUMENTED, and this tier exists because that is a different
    question from what should be indexed.

    @brief Build the whole-repo index scope.
    @return The whole-repo scope.
    @version 2
    """
    root = Path(repo_root).expanduser().resolve()
    ignored = _gitignored_paths(root)
    ## A SUBMODULE'S OWN `.gitignore` IS INVISIBLE TO THE PARENT. `git ls-files` stops
    ## at a submodule boundary, so the sweep above reports nothing inside a nested
    ## tree — and a nested tree is now INDEXED rather than excluded, which is exactly
    ## when its build output starts to matter. Asked per nested repo instead.
    for nested in nested_repo_roots(root):
        ignored.extend(_gitignored_paths(nested))
    excludes = [*ignored, *_pruned_dirs(root, set(ignored))]
    return DerivedScope(
        source=SOURCE_WHOLE_REPO,
        ## PRESENT-BUT-UNUSABLE IS NOT ABSENT (gh#5). A declaration carrying an `index_scope:`
        ## that yields no roots used to land here and report "no index_scope is declared" — while
        ## the loader had already logged "<file> declares index_scope" seconds earlier. A reporter
        ## got both lines from one build and could not tell whether to fix their YAML or file a
        ## bug; only `propose_declaration` settled it, and nobody reaches for that after a build
        ## reports success. `rejected` REPLACES the absence clause, never appends to it.
        reason=(
            (rejected if rejected else f"no {INDEX_SCOPE_SECTION} is declared for this repo")
            + f" — {_guard_config_note(root, guard_config)} — so the whole repository is the "
            f"index scope, INCLUDING any nested git trees, less the paths git ignores "
            f"and the dot/cache directories. A Doxyfile, if the repo ships one, still "
            f"supplies ALIASES and PREDEFINED but no longer supplies the INPUT: that is "
            f"a documentation target, not a reasoning boundary. {_declaration_advice()}"
        ),
        roots=(root,),
        excludes=tuple(excludes),
    )


## @brief Directories holding their own git tree anywhere under a repo root.
## @param repo_root Repo root to walk.
## @return Absolute paths of nested repository directories, outermost first.
## @version 1
## @req REQ-DDB-CONFIG-001
def nested_repo_roots(repo_root: Path) -> list[Path]:
    """THE SAME WALK THAT USED TO EXCLUDE THESE TREES, made public so gh#335 can tag
    them instead. The pipeline already computed this answer on every build and threw
    it away into a WARNING — the identical shape as the scope provenance that gh#319
    persisted, and as the macro hop doxygen was already emitting.

    A directory holding `.git` is a DIFFERENT repository. That is the ONLY test, and
    the rule is deliberately not name-based: `vendor/` and `third_party/` are
    conventions, not facts, and a copied-in third-party header with no git tree of its
    own IS first party — the repo committed it and owns it, so its metrics should say
    so.

    The root ITSELF is never nested, so a root that IS a repository does not report
    itself.

    @brief Find the nested git trees under a repo root.
    @return Absolute paths of nested repository directories.
    @version 1
    """
    return _nested_repos_under(Path(repo_root).expanduser().resolve())


## @brief Nested trees the repo itself DECLARES as dependencies (submodule gitlinks).
## @param repo_root Repo root to walk.
## @return Absolute paths of declared dependency trees, outermost first.
## @version 1
## @req REQ-DDB-CONFIG-001
def dependency_roots(repo_root: Path) -> list[Path]:
    """THE SUBSET OF `nested_repo_roots` THE PARENT OWNS UP TO. Two questions were being
    answered by one predicate until gh#352 half 2: descent (does this tree hide its own build
    output from its parent?) and ownership (is this somebody else's code?). Both walks are the
    same walk; only the filter differs, so they share `_nested_repos_under` and diverge here.

    Descent must see every separate git tree, including a developer's stray clone, because
    `git ls-files` stops at any tree boundary. Ownership must see only what the repository
    committed as a gitlink — see `_is_dependency_of_parent` for the measurement that forced
    the split.

    @brief List the nested trees the repo declares as dependencies.
    @return Absolute paths of dependency trees.
    @version 1
    """
    return [n for n in nested_repo_roots(repo_root) if _is_dependency_of_parent(n)]


## @brief Paths the repo's own git configuration ignores.
## @param root Resolved repo root.
## @return Absolute paths of ignored files and wholly-ignored directories.
## @version 2
## @dg_internal
def _gitignored_paths(root: Path) -> list[Path]:
    """`.gitignore` is the one scope declaration essentially every repo already
    writes, and it names exactly the trees the whole-repo tier must not swallow: the
    virtualenv, the build output, the tool caches, the vendored checkout.

    `--directory` collapses a wholly-ignored directory into a single entry, so the
    result is a handful of paths rather than one per ignored file.

    Git being absent, or the tree not being a repository, yields no exclusions and
    says so: the scope still works, it is just wider than the repo asked for, and a
    silently wider index is the outcome this project keeps paying for.

    @brief List the paths git ignores under a repo root.
    @return Absolute ignored paths.
    @version 2
    """
    command = [
        "git",
        "-C",
        str(root),
        "ls-files",
        "-z",
        "--others",
        "--ignored",
        "--exclude-standard",
        "--directory",
    ]
    try:
        ## `env=git_env()` and NOT the inherited environment: `git -C <root>` is OUTRANKED
        ## by an absolute `GIT_DIR`, which git exports to every hook it runs — so without
        ## this the ignore list belongs to whatever repository invoked us. See `gitenv`.
        proc = subprocess.run(command, capture_output=True, text=True, check=False, env=git_env())
    except OSError as exc:
        logger.warning("index_scope: git is unavailable (%s) — nothing ignored was excluded", exc)
        return []
    if proc.returncode != 0:
        logger.warning(
            "index_scope: %s is not a git repository (git exit %d) — nothing ignored was "
            "excluded from the whole-repo scope",
            root,
            proc.returncode,
        )
        return []
    return [(root / entry).resolve() for entry in proc.stdout.split("\0") if entry]


## @brief Dot and cache directories anywhere under a whole-repo root.
## @param root Resolved repo root.
## @param already Paths already excluded, which are neither re-reported nor walked.
## @return Absolute paths of directories the index should never be handed.
## @version 2
## @dg_internal
def _pruned_dirs(root: Path, already: set[Path]) -> list[Path]:
    """`_skip_dir` is this module's rule for a directory no repo declares and none
    wants indexed. Under a declared root it is applied by pruning the walk that
    builds the roots; the whole-repo root is never walked for its files, so the same
    rule has to reach doxygen as EXCLUDE entries instead.

    @brief Collect the dot/cache directories a whole-repo scope must exclude.
    @return Absolute directory paths.
    @version 1
    """
    found: list[Path] = []
    for dirpath, dirnames, _ in os.walk(root, onerror=_warn_unwalkable):
        here = Path(dirpath)
        if len(here.relative_to(root).parts) >= _MAX_DEPTH:
            logger.warning(
                "index_scope: depth limit reached under %s — not pruning below %s", root, here
            )
            _DEPTH_LIMITED.append(here)
            dirnames[:] = []
            continue
        dirnames[:] = _descendable(here, dirnames, already, found)
    return found


## @brief Split one directory's children into those worth walking and those to exclude.
## @param here The directory being walked.
## @param dirnames Its child directory names.
## @param already Paths already excluded.
## @param found Accumulator for newly-excluded directories.
## @return The child names the walk should descend into.
## @version 2
## @dg_internal
def _descendable(
    here: Path, dirnames: list[str], already: set[Path], found: list[Path]
) -> list[str]:
    """A NESTED REPOSITORY IS DESCENDED INTO (gh#333). It used to be skipped here,
    which was consistent while the scope excluded it wholesale; now that it is indexed
    and tagged, skipping it would leave its `.git` object store and its caches as the
    one part of the tree nothing prunes. `_skip_dir` catches `.git` itself, because it
    is a dot-directory like any other.

    @brief Choose which child directories to descend into.
    @return Descendable child names.
    @version 2
    """
    keep: list[str] = []
    for name in dirnames:
        child = here / name
        if any(_is_within(child, path) for path in already):
            continue
        if _skip_dir(name):
            found.append(child)
            continue
        keep.append(name)
    return keep


## @brief Index scope declared directly in the repo's `.clew.yaml`.
## @param root Resolved repo root.
## @param guard_config Explicit guard-config path overriding discovery, or None.
## @return A DerivedScope when `index_scope:` is declared and usable, else None.
## @version 9
## @dg_internal
def _declared_index_scope(
    root: Path, guard_config: Path | str | None = None, stated: dict | None = None
) -> DerivedScope | None:
    """Read an explicit `index_scope:` declaration::

        index_scope:
          roots:    [clew, scripts, tests]
          excludes: [tests/fixtures]

    Roots are repo-relative so the declaration stays portable. A root that does
    not exist is dropped with a warning rather than passed to doxygen, which
    would otherwise emit a confusing "input not found" for a stale entry.

    Returns None when nothing usable is declared, which drops the resolution to the
    Doxyfile's own INPUT and then to the whole repository — the zero-config default
    for every repo that says nothing.

    An `index_scope:` may also arrive through the guard config's `x-clew`
    passthrough, which is why the override is threaded this far down: before gh#16 that
    passthrough was read from the repo root only, so a repo declaring its index scope
    inside a `conf/` guard config got a whole-repo scope with nothing said.

    A declared root is TAKEN AT ITS WORD AND NEVER WALKED, which is the whole point —
    and which means a clone of another repository beneath it is indexed with no walk
    to notice. Since gh#333 that is no longer a hazard to close but the behaviour to
    have: `external.py` walks for those trees after the build and TAGS their rows, so
    two codebases in one index can still be told apart in an answer.

    @brief Load a declared index scope.
    @return DerivedScope or None.
    @version 9
    """
    from .declaration import (
        DECLARATION_NAME,
        load_declaration_located,
    )

    if stated:
        ## gh#382 tier 1. Built through the SAME construction as a declared one, so a stated
        ## scope cannot differ from a written one in which paths it drops or how it reports
        ## itself. Only `reason` differs, and it has to: an owner reading "declared in
        ## <file>" for a scope that came from a tool call would go and edit a file that says
        ## nothing, which is the checkable-and-wrong attribution this function already fixed
        ## once for the `x-` passthrough.
        declaration, source_path = {INDEX_SCOPE_SECTION: stated}, None
    else:
        declaration, source_path = load_declaration_located(root, guard_config)
    section = declaration.get(INDEX_SCOPE_SECTION)
    if section is None:
        return None
    where = str(source_path) if source_path else "the stated declaration"
    if not isinstance(section, dict):
        return _Rejected(
            f"{where} carries an {INDEX_SCOPE_SECTION} that is "
            f"{type(section).__name__}, not a mapping"
        )

    ## FAIL CLOSED AT THE ENTRY LEVEL, WHICH IS THE QUIETER ONE. The section name is validated
    ## against KNOWN_SECTIONS; the keys INSIDE it were not, so `exclude:` for `excludes:` parsed
    ## to a perfectly valid mapping that no consumer read. gh#5's reporter wrote exactly that,
    ## got "no index_scope is declared", and could not tell a schema slip from a bug. An
    ## accepted-but-unread key is this project's most repeated defect; this closes one more.
    unknown = sorted(str(k) for k in section if str(k) not in _INDEX_SCOPE_KEYS)
    if unknown:
        return _Rejected(
            f"{where} declares {INDEX_SCOPE_SECTION} with unknown key(s) "
            f"{', '.join(unknown)} — the accepted keys are "
            f"{', '.join(sorted(_INDEX_SCOPE_KEYS))}"
        )

    roots = _existing_paths(root, section.get("roots") or [], "root")
    if not roots:
        return _Rejected(
            f"{where} declares {INDEX_SCOPE_SECTION} but no usable `roots:` — `roots` REPLACES "
            f"the index scope and is REQUIRED; `excludes` alone does nothing, and a root that "
            f"does not exist on disk is dropped"
        )
    excludes = _existing_paths(root, section.get("excludes") or [], "exclude")
    return DerivedScope(
        source=SOURCE_DECLARED,
        ## NAMES THE FILE IT WAS ACTUALLY READ FROM. This said
        ## `<root>/.clew.yaml` unconditionally, so a declaration carried by the
        ## guard config's `x-` passthrough was attributed to a file that need not exist —
        ## checkable and wrong, which sends an owner to edit nothing.
        reason=(
            f"{INDEX_SCOPE_SECTION} stated by the caller (tier 1)"
            if stated
            else f"{INDEX_SCOPE_SECTION} declared in {source_path or root / DECLARATION_NAME}"
        ),
        roots=tuple(roots),
        excludes=tuple(excludes),
    )


## @brief Directories holding a `.git` strictly beneath one declared root.
## @param input_root Declared INPUT root to search under.
## @return Absolute paths of nested repository directories, outermost first.
## @version 3
## @dg_internal
def _nested_repos_under(input_root: Path) -> list[Path]:
    """A BOUNDED walk, not `rglob`. `rglob` would descend into the object stores of the
    repositories it finds and swallow an unreadable directory silently — and a swallowed
    error here reads exactly like "no nested repository", which is the answer that lets
    a foreign codebase into the index. `onerror` therefore WARNS: a directory we could
    not read is a gap in the check, not a clean result.

    Descent stops at a nested repository (its own nested repositories are already
    excluded with it) and at `_MAX_DEPTH`. The root itself never counts, so declaring a
    directory that IS a repository does not exclude the whole scope.

    @brief Find nested repositories under one declared root.
    @return Paths of nested repository directories.
    @version 2
    """
    found: list[Path] = []
    for dirpath, dirnames, _ in os.walk(input_root, onerror=_warn_unwalkable):
        here = Path(dirpath)
        if here != input_root and _holds_git_tree(here):
            found.append(here)
            dirnames[:] = []
            continue
        if len(here.relative_to(input_root).parts) >= _MAX_DEPTH:
            logger.warning(
                "index_scope: depth limit reached under %s — not checking %s for nested "
                "repositories",
                input_root,
                here,
            )
            _DEPTH_LIMITED.append(here)
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if not _skip_dir(d)]
    return found


## @brief Whether a directory owns a git tree, as a SUBMODULE or as a clone.
## @param directory Directory to test.
## @return True when the directory holds a `.git` entry of either kind.
## @version 2
## @dg_internal
def _holds_git_tree(directory: Path) -> bool:
    """A SUBMODULE'S `.git` IS A FILE, NOT A DIRECTORY, and missing that made the
    whole nested-tree feature blind to the case it was built for. A `git submodule`
    checkout writes a 44-byte `gitdir: ../../.git/modules/<name>` POINTER file where
    a standalone clone has a directory — so `".git" in dirnames`, which is what this
    used to be, found nested CLONES and silently skipped every submodule.

    Measured on [tvanfossen/entropic](https://github.com/tvanfossen/entropic), which
    wraps llama.cpp as a submodule: the directory test reported 28 nested trees and
    `extern/llama.cpp` was not among them, while reporting 28 hits made the detector
    look like it was working. Every unit fixture used a `.git` DIRECTORY, so nothing
    in the suite could have caught it — the fixture matched the detector rather than
    the world.

    `exists()` covers both, and covers a worktree's `.git` file too.

    THIS PREDICATE ANSWERS EXACTLY ONE QUESTION — "is there a separate git tree here?" — and
    gh#352 half 2 first tried to make it answer two. Folding the gitlink test in (below) broke
    the OTHER consumer: `_whole_repo_scope` walks these trees to honour each one's own
    `.gitignore`, because `git ls-files` stops at any tree boundary, submodule or clone alike.
    A developer's nested clone still hides its build output from its parent, so descent has to
    see it whether or not the parent declared it. Ownership is a different question with a
    different predicate — see `_is_dependency_of_parent`.

    @brief Test whether a directory holds its own git tree.
    @return True for a nested clone, submodule or worktree.
    @version 2
    """
    return (directory / ".git").exists()


## @brief Does the enclosing repository record this directory as a gitlink (a submodule)?
## @param directory Candidate nested-tree directory.
## @return True when the parent tracks it as mode 160000; False when it tracks its files, or on any doubt.
## @version 2
## @dg_internal
def _is_dependency_of_parent(directory: Path) -> bool:
    """ASKS THE PARENT, because the parent is the only thing that knows whether this directory
    is a dependency it declared or code it owns. `git ls-files -s` on the path prints the mode:
    160000 is a gitlink (a submodule), 100644/100755 are ordinary blobs the parent committed.

    FAIL-CLOSED MEANS FIRST PARTY HERE, which is the opposite of the usual direction and is
    deliberate. Every other fail-closed rule in this pipeline widens what it suspects; this one
    narrows, because the cost is asymmetric: tagging first-party code as somebody else's makes a
    repo's OWN symbols vanish from the default first-party counts, while missing a submodule tag
    only leaves an external tree counted as first party — visible, and correctable. When git
    cannot answer (not a repo, git absent, an error), the answer is "the parent does not record
    this as a dependency".

    WHY THE FILESYSTEM IS NOT ENOUGH, measured. A `.git` in a directory says somebody has a
    repository THERE; it does not say the parent treats that directory as somebody else's code.
    The two diverge in a case that is common: a developer clone left inside a directory whose
    files the parent TRACKS. Then the tag becomes a property of the WORKING COPY rather than of
    the repository — the same commit produces two different indexes depending on who built it,
    and one of them reports the repo's own code as external.

    On [tvanfossen/entropic](https://github.com/tvanfossen/entropic) three roots were tagged
    external while `.gitmodules` declares ONE. `git ls-files -s examples/explorer
    examples/pychess` returns mode 100644 BLOBS, not gitlinks — those files are entropic's own,
    committed by entropic, and entropic's to change. A rubric mark grading "states that
    extern/llama.cpp is the only submodule" was being steered to answer "three".

    This is the dual of gh#335's rule. That one says external is a git TREE and never a
    directory NAME, which killed the `vendor/`/`third_party/` heuristic. This one says a git
    tree is not automatically a git DEPENDENCY.

    @brief Test whether the parent records this directory as a submodule gitlink.
    @return True only on a positive gitlink reading.
    @version 2
    """
    parent = directory.parent
    try:
        ## `env=git_env()` for the same reason as the ignore listing above, and it matters
        ## MORE here: `cwd=parent` is what makes this a question about the parent, and an
        ## inherited `GIT_DIR` overrides cwd entirely — so the gitlink probe answered about
        ## the hook's repository and returned False for every real submodule.
        proc = subprocess.run(
            ["git", "ls-files", "-s", "--", directory.name],
            cwd=str(parent),
            capture_output=True,
            text=True,
            check=False,
            env=git_env(),
        )
    except OSError:
        return False
    if proc.returncode != 0 or not proc.stdout.strip():
        return False
    ## `160000 <sha> 0\t<path>` for a gitlink. Read the MODE field rather than matching the
    ## whole line, so a path containing whitespace cannot change the answer.
    return any(line.split(" ", 1)[0] == "160000" for line in proc.stdout.splitlines() if line)


## @brief Report a directory the nested-repository check could not read.
## @param error The OSError os.walk raised.
## @version 1
## @dg_internal
def _warn_unwalkable(error: OSError) -> None:
    """@brief Warn that a directory was unreadable, so a gap never reads as a pass."""
    logger.warning(
        "index_scope: could not read %s (%s) — it was NOT checked for a nested repository",
        getattr(error, "filename", "?"),
        error,
    )


## @brief Whether a path is the same as, or inside, another.
## @param path Candidate path.
## @param ancestor Path that may contain it.
## @return True when `path` is `ancestor` or lies beneath it.
## @version 1
## @dg_internal
def _is_within(path: Path, ancestor: Path) -> bool:
    """@brief Containment test used to suppress already-declared exclusions."""
    return path == ancestor or ancestor in path.parents


## @brief Resolve declared repo-relative entries that exist on disk.
## @param root Repo root the entries are relative to.
## @param entries Declared relative path strings.
## @param label Word used in the warning for a missing entry.
## @return Absolute paths that exist.
## @version 1
## @dg_internal
def _existing_paths(root: Path, entries: list, label: str) -> list[Path]:
    """@brief Resolve declared paths, warning about (and dropping) missing ones."""
    found = []
    for entry in entries:
        path = (root / str(entry)).resolve()
        if path.exists():
            found.append(path)
        else:
            logger.warning(
                "index_scope %s %r does not exist under %s — ignoring", label, entry, root
            )
    return found


## @brief Where a declaration was looked for, phrased for a fallback reason.
## @param root Resolved repo root.
## @param guard_config Explicit guard-config path overriding discovery, or None.
## @return A clause naming the located config, or every location that was searched.
## @version 2
## @req REQ-DDB-CONFIG-001
def _guard_config_note(root: Path, guard_config: Path | str | None) -> str:
    """SAY WHERE WE LOOKED, BEFORE FALLING BACK. This clause is the substance of
    gh#16: a repo whose scope cannot be derived gets a DIFFERENT tree indexed than it
    declares, and without this the only evidence is a warning naming one file — so
    "this repo declares no scope" and "we looked in the wrong place for its config"
    produce the same message.

    A config that WAS found and still yielded no scope is worth saying too, and is no
    contradiction: the `x-clew` passthrough is optional, so a guard config can
    be present, valid, and silent about the index.

    @brief Describe the declaration search for a fallback reason.
    @return A human-readable clause.
    @version 2
    """
    location = discover_guard_config(root, guard_config)
    if location.path is None:
        return f"no doxygen-guard config was found (searched {location.describe_search()})"
    return (
        f"a doxygen-guard config WAS found at {location.path} (via {location.source}), but it "
        f"carries no {INDEX_SCOPE_SECTION}"
    )


## @brief Derive a scope and log which scope was used and why.
## @param repo_root Repo root to derive scope for.
## @param guard_config Explicit guard-config path overriding discovery, or None.
## @return The derived (or whole-repo) scope.
## @version 6
## @req REQ-DDB-CONFIG-001
def derive_scope_logged(
    repo_root: Path, guard_config: Path | str | None = None, stated: dict | None = None
) -> DerivedScope:
    """Fail SAFE and LOUD: a declared derivation logs its roots at INFO, the
    whole-repo default logs its reason at WARNING so a boundary nobody chose is never
    mistaken for one somebody did.

    The undeclared branch no longer says "falling back to the Doxyfile INPUT", which
    since gh#333 would be a checkable and wrong statement about what got indexed —
    the same defect class as stamping `source: doxyfile` on a whole-repo build.

    @brief Derive the index scope with an explicit log line.
    @return The derived (or whole-repo) scope.
    @version 6
    """
    scope = derive_scope(repo_root, guard_config, stated)
    if scope.is_derived():
        logger.info(
            "scope: declared — %s — %d INPUT root(s), %d EXCLUDE(s): %s",
            scope.reason,
            len(scope.roots),
            len(scope.excludes),
            ", ".join(str(p) for p in scope.roots),
        )
    else:
        logger.warning("scope: indexing the WHOLE repository — %s", scope.reason)
    return scope
