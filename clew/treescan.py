# SPDX-License-Identifier: MIT
"""File-identity hashing and indexed-tree enumeration for incremental builds.

Split from `indexcache` by responsibility: this module answers "what files does
this build read, and what is each one's identity?" — the filesystem side —
while `indexcache` owns the sidecar SQLite store.

**Content hash, not mtime, is the authority.** `size + mtime_ns` is a cheap
PREFILTER that lets an unchanged file skip re-hashing; the sha256 of its bytes
decides whether it counts as changed. That is what makes a `touch` with no edit
and a branch checkout that restores identical content stay cache HITS, which
mtime alone cannot do.

@brief Content hashing + doxygen INPUT tree enumeration.
@version 1
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from pathlib import Path

_HASH_CHUNK = 1 << 20


## @brief One file's cheap identity (size + mtime) plus its authoritative sha.
## @version 1
class FileIdentity:
    """A file's `st_size`/`st_mtime_ns` prefilter pair and its content sha256.

    @brief Per-file identity record.
    @version 1
    """

    __slots__ = ("content_sha", "mtime_ns", "size_bytes")

    ## @brief Store one file's size, mtime_ns, and content sha.
    ## @version 1
    ## @dg_internal
    def __init__(self, size_bytes: int, mtime_ns: int, content_sha: str) -> None:
        self.size_bytes = size_bytes
        self.mtime_ns = mtime_ns
        self.content_sha = content_sha


## @brief Result of classifying a scanned tree against the previous scan.
## @version 1
class ScanSummary:
    """Repo-relative paths bucketed unchanged / modified / added / removed.

    @brief Change classification of one tree scan.
    @version 1
    """

    __slots__ = ("added", "modified", "removed", "unchanged")

    ## @brief Store the four change buckets.
    ## @version 1
    ## @dg_internal
    def __init__(
        self,
        unchanged: list[str],
        modified: list[str],
        added: list[str],
        removed: list[str],
    ) -> None:
        self.unchanged = unchanged
        self.modified = modified
        self.added = added
        self.removed = removed

    ## @brief Human-readable one-line summary for logging.
    ## @return "N unchanged, N modified, N added, N removed".
    ## @version 1
    ## @req REQ-DDB-PIPE-003
    def describe(self) -> str:
        return (
            f"{len(self.unchanged)} unchanged, {len(self.modified)} modified, "
            f"{len(self.added)} added, {len(self.removed)} removed"
        )


## @brief sha256 of a file's bytes, streamed in chunks.
## @return Lowercase hex sha256 digest, or "" when the file cannot be read.
## @version 2
## @req REQ-DDB-INDEX-002
def hash_file(path: Path) -> str:
    """Stream a file through sha256. Unreadable files hash to "" so they are
    treated as perpetually-changed (fail toward a MISS, never a false hit).

    @brief Content sha256 of one file.
    @version 2
    """
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(_HASH_CHUNK):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


## @brief sha256 of a manifest's content, for folding into a stage cache key.
## @param source Manifest path, an already-parsed mapping, or None.
## @return Hex digest of the content, "" for None, "missing" when unreadable.
## @version 3
## @req REQ-DDB-PIPE-003
def manifest_key(source: Path | dict | None) -> str:
    """Hash an optional manifest (--thread-patterns / --shared-key-patterns /
    --mqtt-dispatch / --data-model / --guard-config). Its CONTENT changes what
    the per-file extractors emit, so it belongs in the affected stage's key.

    A manifest can now arrive as a section of the repo's `.clew.yaml` rather
    than as a file, so a MAPPING is hashed by its canonical serialization. That
    keeps the invalidation property intact — editing a declaration must re-run
    the stages it feeds, exactly as editing a standalone manifest does.

    @brief Cache-key contribution of an optional manifest.
    @version 3
    """
    if source is None:
        return ""
    if isinstance(source, dict):
        canonical = json.dumps(source, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()
    sha = hash_file(source)
    return sha or "missing"


## @brief Repo-root-relative string for a path, or its absolute form if outside.
## @return Path string used as the `source_files` key.
## @version 1
## @req REQ-DDB-PIPE-003
def rel_key(path: Path, repo_root: Path) -> str:
    """@brief Key a scanned path the same way doxygen's `path` table does."""
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


## @brief True when `path` sits under any of the excluded roots.
## @return True if the path is inside an exclude root (or is one).
## @version 1
## @dg_internal
def _is_excluded(path: Path, excludes: list[Path]) -> bool:
    return any(path == ex or ex in path.parents for ex in excludes)


## @brief Regular files under one INPUT root, skipping EXCLUDE subtrees unvisited.
## @param root INPUT root to expand (may itself be a file).
## @param excludes EXCLUDE roots, pruned during descent rather than filtered after.
## @return List of regular files under the root (the root itself when a file).
## @version 1
## @dg_internal
def _files_under(root: Path, excludes: list[Path]) -> list[Path]:
    """PRUNE DURING THE WALK. An excluded directory is never descended into, so
    the scan is sized by what survives rather than by what the repository holds.
    Enumerating first and testing each path afterwards costs
    O(files x excludes x depth) over a set that is mostly discarded: on a repo
    indexed at the whole-repo scope tier, `.git`, `.venv` and build output are
    walked in full only to be dropped, and the exclusion test alone then
    dominates a warm refresh.

    The surviving set is unchanged. Three cases keep it that way: a root whose
    own ancestor is excluded contributes nothing, an exclude naming a FILE is
    matched exactly, and `is_file()` still decides membership so a broken
    symlink or a directory entry is dropped as before. Symlinked directories
    stay un-followed, matching the recursive-glob behaviour this replaces.

    @brief Files under one root with excluded subtrees pruned.
    @version 1
    """
    if _is_excluded(root, excludes):
        return []
    if root.is_file():
        return [root]
    if not root.is_dir():
        return []
    excluded = frozenset(excludes)
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        dirnames[:] = [name for name in dirnames if (here / name) not in excluded]
        for name in filenames:
            path = here / name
            if path not in excluded and path.is_file():
                found.append(path)
    return found


## @brief Enumerate every file doxygen would read, honouring EXCLUDE roots.
## @return Mapping of repo-relative path string to its absolute path.
## @version 3
## @req REQ-DDB-INDEX-002
def enumerate_tree(roots: list[Path], excludes: list[Path], repo_root: Path) -> dict[str, Path]:
    """Walk the INPUT roots recursively (the pipeline forces RECURSIVE=YES) and
    drop anything under an EXCLUDE root. Deliberately NOT extension-filtered:
    hashing every file under INPUT means any change at all forces a doxygen
    re-run, which is the conservative side of the "when in doubt, MISS" rule.

    THAT CONSERVATISM IS FREE ON THE HOT PATH, so it is kept whole. What a warm
    refresh actually costs is the WALK, not the hash: `size + mtime_ns` lets an
    unchanged file skip re-hashing, so a refresh that reprocesses nothing hashes
    nothing. Sizing the walk to the surviving set — `_files_under` prunes
    excluded subtrees instead of enumerating and discarding them — leaves every
    file's identity, and therefore every invalidation, exactly as it was. An
    extension filter would trade a documented safety property for a saving the
    prefilter already delivers.

    @brief Enumerate the indexed file tree.
    @version 3
    """
    found: dict[str, Path] = {}
    for root in roots:
        for path in _files_under(root, excludes):
            found[rel_key(path, repo_root)] = path
    return found


## @brief Whether adding extra INPUT clears the Doxyfile's own EXCLUDE list.
## @param extra_input The --extra-input entries, possibly None or empty.
## @return True when the repo's own EXCLUDE is dropped in favour of --extra-exclude.
## @version 1
## @req REQ-DDB-PIPE-003
def extra_input_clears_exclude(extra_input: list[str] | None) -> bool:
    """ONE rule, previously spelled out twice in two files.

    `doxygen._build_doxyfile_content` emits `EXCLUDE =` (clearing it) whenever any
    extra INPUT is present, so submodule source added via `--extra-input` is not
    silently dropped by the target's own EXCLUDE. `doxygen_input_roots` has to
    MIRROR that exactly, or the incremental cache would hash a different file set
    than doxygen reads — a cache that can answer "unchanged" about a tree it
    enumerated wrongly.

    Both call sites now ask this function instead of each re-deriving `bool(...)`
    from `extra_input`. The two implementations were correct and identical today;
    they were also free to drift, with the only symptom a cache-hit rate that is
    subtly wrong. Naming the rule once makes a change to it land in one place and
    makes the coupling greppable.

    Deliberately NOT an attempt to share the text emission itself: one call site
    produces Doxyfile DIRECTIVES incrementally and the other produces RESOLVED
    PATH LISTS, and the emitted bytes are hashed for the index cache, so unifying
    the media would change cache keys for no correctness gain.

    @brief The extra-input-clears-EXCLUDE rule, stated once.
    @version 1
    """
    return bool(extra_input)


## @brief Does a filename match any doxygen FILE_PATTERNS glob?
## @param name Bare filename (no directories), as doxygen matches it.
## @param patterns Effective FILE_PATTERNS globs.
## @return True when doxygen would read a file of this name.
## @version 1
## @dg_internal
def _matches_file_patterns(name: str, patterns: list[str]) -> bool:
    """CASE-INSENSITIVE, and that choice is a fail-safe rather than a fidelity
    claim. The two possible errors are not symmetric: flagging a root doxygen would
    have read refuses a build that works, while missing one leaves the pre-existing
    silent behaviour. Lowercasing admits MORE files and so flags FEWER roots, which
    is the safe direction for a check whose consequence is a hard failure.

    @brief Match a filename against FILE_PATTERNS.
    @version 1
    """
    lowered = name.lower()
    return any(fnmatch.fnmatch(lowered, pattern.lower()) for pattern in patterns)


## @brief --extra-input roots that hold files but none doxygen will read (gh#3).
## @param doxyfile Doxyfile whose FILE_PATTERNS decide what is read.
## @param work_dir Directory --extra-input entries resolve against (the Doxyfile's).
## @param extra_input The user-supplied --extra-input entries.
## @param extra_exclude The user-supplied --extra-exclude entries.
## @param repo_root Repo root, for enumeration keying.
## @return Resolved roots whose every file is excluded by FILE_PATTERNS.
## @version 3
## @req REQ-DDB-INDEX-001
def roots_matching_no_file_pattern(
    doxyfile: Path,
    work_dir: Path,
    extra_input: list[str] | None,
    extra_exclude: list[str] | None,
    repo_root: Path,
) -> list[Path]:
    """Find the gh#3 silent drop: a root the user ASKED to have indexed whose files
    doxygen reads and discards, because nothing in this pipeline sets FILE_PATTERNS
    and the target's own declaration therefore applies to every appended
    `INPUT +=` line.

    THE DISCRIMINATOR IS "holds files, and none of them match" — never "contributed
    nothing". An empty directory and an absent path also contribute nothing, and
    FILE_PATTERNS is not why; blaming the patterns for those would be a guard that
    fires on the benign case, which this project has shipped once already and which
    trains the reader to ignore the message in the case that matters. Requiring at
    least one present-and-excluded file makes the check structurally unable to fire
    on an empty root, rather than merely unlikely to.

    The invisibility this recovers is worth naming: `enumerate_tree` is deliberately
    NOT extension-filtered, so the incremental cache happily hashes files doxygen
    will never read. The drop is therefore absent from the cache AND from the logs,
    and the only pre-existing signal — `warn_if_no_function_bodies` — fires solely
    when ZERO implementation bodies exist anywhere, which a header-only target
    legitimately satisfies.

    @brief Roots whose files are all excluded by FILE_PATTERNS.
    @return The offending resolved roots, empty when every root contributes.
    @version 3
    """
    from .doxygen import effective_file_patterns

    if not extra_input:
        return []
    patterns = effective_file_patterns(doxyfile)
    excludes = [(work_dir / entry).resolve() for entry in extra_exclude or []]
    offenders: list[Path] = []
    for entry in extra_input:
        root = (work_dir / entry).resolve()
        present = _files_under(root, excludes)
        if not present:
            continue  # empty or absent: the patterns are not the reason
        if not any(_matches_file_patterns(p.name, patterns) for p in present):
            offenders.append(root)
    return offenders


## @brief Resolve the Doxyfile's INPUT/EXCLUDE lists into absolute roots.
## @return (input roots, exclude roots), matching what the pipeline feeds doxygen.
## @version 4
## @req REQ-DDB-PIPE-003
def doxygen_input_roots(
    doxyfile: Path,
    work_dir: Path,
    extra_input: list[str] | None,
    extra_exclude: list[str] | None,
    replace_input: bool = False,
) -> tuple[list[Path], list[Path]]:
    """Mirror `doxygen._build_doxyfile_content`'s semantics exactly: extra
    INPUT paths are appended, and when any are given the Doxyfile's own
    EXCLUDE list is CLEARED and only `--extra-exclude` applies. With
    `replace_input` the Doxyfile's INPUT is cleared too, so the extra roots
    ARE the scope. Reading the DECLARED lists (never hardcoding a repo's
    layout) keeps the enumeration correct for any target repo.

    The extra-input-clears-EXCLUDE rule is asked of `extra_input_clears_exclude`
    rather than re-derived here, so the mirror of `_build_doxyfile_content` cannot
    drift silently (gh#3).

    @brief Enumerate the doxygen INPUT/EXCLUDE roots.
    @version 4
    """
    from .doxygen import parse_doxyfile_values

    declared = [] if (replace_input and extra_input) else parse_doxyfile_values(doxyfile, "INPUT")
    inputs = declared + list(extra_input or [])
    excludes = (
        list(extra_exclude or [])
        if extra_input_clears_exclude(extra_input)
        else parse_doxyfile_values(doxyfile, "EXCLUDE")
    )
    return (
        [(work_dir / entry).resolve() for entry in inputs],
        [(work_dir / entry).resolve() for entry in excludes],
    )
