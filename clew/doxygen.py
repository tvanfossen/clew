# SPDX-License-Identifier: MIT
"""Doxygen invocation, output handling, and Doxyfile parsing.

`run_doxygen` spawns the doxygen binary with our augmented Doxyfile,
streams its stdout to drive a Rich progress bar, and verifies the
generated SQLite DB exists. `copy_database` moves the result.
`fix_doxygen_paths` undoes STRIP_FROM_PATH so paths in the DB
resolve relative to the target repo root (the reader/annotator need
that to actually open files).

@brief Doxygen runner + output post-processing.
@version 2
"""

from __future__ import annotations

import fnmatch
import shutil
import sqlite3
import subprocess
import threading
import sys
from pathlib import Path, PurePosixPath

from ._common import active_console, clean_subprocess_env, logger, make_progress
from .errors import DoxygenUnavailableError

_DOXYFILE_FORCED_FLAGS = (
    "\nGENERATE_SQLITE3 = YES\n"
    "REFERENCES_RELATION = YES\n"
    "REFERENCED_BY_RELATION = YES\n"
    "CALL_GRAPH = YES\n"
    "CALLER_GRAPH = YES\n"
    "HAVE_DOT = NO\n"
    "PLANTUML_JAR_PATH =\n"
    "PLANTUML_CFG_FILE =\n"
    "EXTRACT_ALL = YES\n"
    "EXTRACT_STATIC = YES\n"
    "EXTRACT_ANON_NSPACES = YES\n"
    "RECURSIVE = YES\n"
    ## NO FILTER MAY EVER RUN. `INPUT_FILTER` and `FILTER_PATTERNS` values are COMMANDS
    ## doxygen executes over each input file, and the target's OWN Doxyfile is read and
    ## honoured — so without these three lines any indexed repository can obtain arbitrary
    ## command execution as the developer by simply DECLARING a filter, no injection and no
    ## cleverness required. clew indexes untrusted third-party code, which makes that a
    ## remote-ish code execution primitive reachable by cloning.
    ##
    ## Forced HERE because this block is concatenated AFTER the repo's Doxyfile, and doxygen
    ## takes the LAST assignment. It is not sufficient on its own: `extra_input` is appended
    ## after this block, so a path that injects its own directive still wins — see
    ## `_reject_uninlineable` for that half.
    "INPUT_FILTER =\n"
    "FILTER_PATTERNS =\n"
    "FILTER_SOURCE_FILES = NO\n"
    ## EVERY REMAINING COMMAND-VALUED OPTION, enumerated from `doxygen -g`'s own template
    ## rather than from memory. The first version of this block forced the three above and
    ## declared the hostile-Doxyfile path closed; `QHG_LOCATION` executed anyway, because
    ## doxygen runs qhelpgenerator and `HTML_EXTRA_FILES` copies a repo file into the output
    ## tree with its exec bit intact to supply the path. Verified against 1.9.8.
    ## `FILE_VERSION_FILTER` is the other one nobody had noticed: a command run per file.
    "FILTER_SOURCE_PATTERNS =\n"
    "FILE_VERSION_FILTER =\n"
    "HHC_LOCATION =\n"
    "QHG_LOCATION =\n"
    "LATEX_CMD_NAME =\n"
    "MAKEINDEX_CMD_NAME =\n"
    "LATEX_MAKEINDEX_CMD =\n"
    "DOT_PATH =\n"
    "DIA_PATH =\n"
    "MSCGEN_TOOL =\n"
    ## EVERY GENERATOR clew does not consume. It reads the sqlite3 database and nothing else —
    ## there is no XML, HTML or LaTeX reader anywhere in `clew/`, so the `cli.py` docstring's
    ## "SQLite + XML" is stale. Each of these carries its own file-and-command surface, and
    ## turning them off removes that surface wholesale instead of key by key. It also makes
    ## builds cheaper, which is a side effect rather than the reason.
    "GENERATE_HTML = NO\n"
    "HTML_EXTRA_FILES =\n"
    "HTML_EXTRA_STYLESHEET =\n"
    "HTML_HEADER =\n"
    "HTML_FOOTER =\n"
    "HTML_STYLESHEET =\n"
    "GENERATE_LATEX = NO\n"
    "LATEX_HEADER =\n"
    "LATEX_FOOTER =\n"
    "LATEX_EXTRA_FILES =\n"
    "GENERATE_MAN = NO\n"
    "GENERATE_RTF = NO\n"
    "GENERATE_XML = NO\n"
    "GENERATE_DOCBOOK = NO\n"
    "GENERATE_AUTOGEN_DEF = NO\n"
    "GENERATE_PERLMOD = NO\n"
    "GENERATE_QHP = NO\n"
    "GENERATE_HTMLHELP = NO\n"
    "GENERATE_ECLIPSEHELP = NO\n"
    "GENERATE_DOCSET = NO\n"
    ## Read-external-file options. Lower severity than a command, but a repo choosing what
    ## clew reads is still a repo influencing the build.
    "LAYOUT_FILE =\n"
    "CITE_BIB_FILES =\n"
    "TAGFILES =\n"
    "GENERATE_TAGFILE =\n"
    "CLANG_DATABASE_PATH =\n"
)

## HOW LONG A SINGLE doxygen RUN MAY TAKE BEFORE IT IS KILLED. A BACKSTOP, NOT A BUDGET — the
## point is that a wedged run ENDS, not that a slow one is punished. Full builds measured here run
## ~5 s (this repo) and ~130 s (a 2,359-file C++ target), so 15 minutes is far outside any
## legitimate run while still bounding the failure the MCP server cannot otherwise recover from:
## it holds its per-target build lock across this call, so one stall queues every later stale
## query in that process forever.
_DOXYGEN_TIMEOUT = 900


_DOXY_PHASE_PREFIXES = ("Generating ", "Building ", "Finished", "Running ")
_DOXY_FILE_PREFIXES = ("Preprocessing ", "Parsing file ")


# Doxygen's OWN default FILE_PATTERNS, and since gh#340 the set every build USES.
#
# NOT a target repo's convention and not a guess — this is the list `doxygen -g`
# writes into a fresh Doxyfile (captured from 1.9.8, the version this pipeline is
# confirmed against), so forcing it is the same kind of default as the forced
# GENERATE_SQLITE3 flags.
#
# "A DECLARED FILE_PATTERNS always wins over it" WAS TRUE AND IS THE DEFECT gh#340
# fixed: a declaration could veto a tree that scope had already admitted. It is now
# forced, below, and a declaration is read only to REPORT the difference.
#
# It also keeps `effective_file_patterns` from ever returning an empty list. Empty
# would make the gh#3 guard conclude that NOTHING matches and flag every root —
# a guard that fires on every benign build, which is the failure mode the guard
# was written to avoid.
DOXYGEN_DEFAULT_FILE_PATTERNS: tuple[str, ...] = (
    "*.c",
    "*.cc",
    "*.cxx",
    "*.cxxm",
    "*.cpp",
    "*.cppm",
    "*.c++",
    "*.c++m",
    "*.java",
    "*.ii",
    "*.ixx",
    "*.ipp",
    "*.i++",
    "*.inl",
    "*.idl",
    "*.ddl",
    "*.odl",
    "*.h",
    "*.hh",
    "*.hxx",
    "*.hpp",
    "*.h++",
    "*.l",
    "*.cs",
    "*.d",
    "*.php",
    "*.php4",
    "*.php5",
    "*.phtml",
    "*.inc",
    "*.m",
    "*.markdown",
    "*.md",
    "*.mm",
    "*.dox",
    "*.py",
    "*.pyw",
    "*.f90",
    "*.f95",
    "*.f03",
    "*.f08",
    "*.f18",
    "*.f",
    "*.for",
    "*.vhd",
    "*.vhdl",
    "*.ucf",
    "*.qsf",
    "*.ice",
)

## gh#340. THE THIRD SCOPE KEY, forced here rather than left to the target. `INPUT` is replaced
## and `EXCLUDE`/`EXCLUDE_PATTERNS` are cleared because a Doxyfile states a DOCUMENTATION target
## while the index states a REASONING boundary — and `FILE_PATTERNS` is the same kind of key,
## which was still being honoured. So a tree that scope ADMITTED could be dropped by an extension
## list, with the build exiting 0 and logging success.
##
## Measured on entropic, the target the submodule feature exists for: it declares
## `*.h *.hpp *.cpp *.md` while the submodule it vendors is `.c`/`.cu`/`.m`, so gh#333 admitted
## llama.cpp and this key then silently dropped it. Its own `main` census lost two `.c`
## definitions the same way, which the rubric had to carry as a population caveat.
##
## Forced to DOXYGEN'S OWN default set, not a list of our choosing: this is what `doxygen -g`
## writes into a fresh Doxyfile, so the build widens to the TOOL's default rather than to a policy
## we invented. Appended after the target's content, so the later assignment wins — the same
## mechanism that makes RECURSIVE stick.
_DOXYFILE_FORCED_FLAGS += f"FILE_PATTERNS = {' '.join(DOXYGEN_DEFAULT_FILE_PATTERNS)}\n"


## @brief The FILE_PATTERNS actually in effect for a build.
## @param doxyfile Doxyfile whose declaration is read (kept for the signature's callers).
## @return The forced pattern set every build now uses.
## @version 2
## @req REQ-DDB-INDEX-001
## @req REQ-DDB-CONFIG-001
def effective_file_patterns(doxyfile: Path) -> list[str]:
    """IT RETURNS WHAT THE BUILD USES, which since gh#340 is the FORCED set and no longer the
    target's declaration. The previous version read the declaration, and leaving it that way
    would have been the sharper half of the bug rather than a leftover: its consumer is the
    gh#3 guard, which exits 1 when a root's every file is excluded by these patterns. Judging
    an added root against a pattern list that no longer governs the build would fail benign
    roots — a guard firing on the ordinary case, from a fix meant to stop a silent veto.

    So the guard now asks the right question and will essentially never fire, because the
    forced set is doxygen's own broad default. That is the correct outcome: the veto it was
    built to detect cannot happen any more. `declared_file_patterns` is what to call when the
    question is what the TARGET asked for — reporting the difference is still worth doing, and
    it is a different question from what the build did.

    @brief Resolve the FILE_PATTERNS doxygen will actually match against.
    @return The forced pattern set.
    @version 2
    """
    return list(DOXYGEN_DEFAULT_FILE_PATTERNS)


## @brief Restrict a file list to what a doxygen run over the roots would actually index.
## @param paths Repo-relative candidate paths.
## @param doxyfile The Doxyfile the build is based on.
## @param honor_exclude_patterns True when the whole-tree run keeps the Doxyfile's
##                              EXCLUDE_PATTERNS, i.e. when it does not replace INPUT.
## @return The subset a directory-driven run would have picked up, in order.
## @version 1
## @req REQ-DDB-INDEX-002
def in_doxygen_scope(paths: list[str], doxyfile: Path, honor_exclude_patterns: bool) -> list[str]:
    """A SCOPE STATEMENT HAS THREE KEYS AND THE TREE SCAN READS ONE. `enumerate_tree` honours
    INPUT and EXCLUDE roots and is DELIBERATELY not extension-filtered — correct for its own
    job, which is deciding WHETHER anything changed ("when in doubt, MISS"). Reusing that
    unfiltered set as the doxygen INPUT is what this fixes: `FILE_PATTERNS` and
    `EXCLUDE_PATTERNS` are the other two keys, and a subset run bypasses both because doxygen
    applies FILE_PATTERNS only to DIRECTORY entries and the run clears EXCLUDE_PATTERNS in
    order to list files individually.

    The consequence measured on the C fixture: a `vendor/` file the Doxyfile excludes by glob
    entered the changed set, was listed explicitly, and was spliced INTO the master — so the
    incremental index held a file no full rebuild would ever produce, with a healthy report and
    nothing in `skipped`. Silently WIDENING scope is worse than narrowing it, because every
    coverage and orphan figure is then computed over a set the operator never asked for.

    EXCLUDE_PATTERNS IS CONDITIONAL, and that asymmetry is deliberate rather than sloppy. A
    repo with a declared scope builds with `replace_input`, which clears EXCLUDE_PATTERNS for
    the WHOLE-TREE run too — so honouring them in the subset would make the subset NARROWER
    than the full build and leave real files stale. The flag says which regime the caller is
    in, so the subset matches whichever one the master was built under.

    @brief Filter a candidate list down to the doxygen run's real scope.
    @return The in-scope subset.
    @version 1
    """
    patterns = effective_file_patterns(doxyfile)
    excluded = parse_doxyfile_values(doxyfile, "EXCLUDE_PATTERNS") if honor_exclude_patterns else []
    kept: list[str] = []
    for rel in paths:
        name = PurePosixPath(rel).name
        if patterns and not any(fnmatch.fnmatch(name, pat) for pat in patterns):
            continue
        if any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch("/" + rel, pat) for pat in excluded):
            continue
        kept.append(rel)
    dropped = len(paths) - len(kept)
    if dropped:
        logger.info(
            "scope: %d of %d candidate file(s) are outside the doxygen run's scope "
            "(FILE_PATTERNS or EXCLUDE_PATTERNS) and are not indexed incrementally either",
            dropped,
            len(paths),
        )
    return kept


## @brief The FILE_PATTERNS a target's own Doxyfile declares, for reporting only.
## @param doxyfile Doxyfile whose declaration is read.
## @return Declared patterns, or [] when the Doxyfile states none.
## @version 1
## @req REQ-DDB-CONFIG-001
def declared_file_patterns(doxyfile: Path) -> list[str]:
    """KEPT BECAUSE THE DECLARATION IS STILL A FACT, just no longer a policy. A target that
    publishes an API reference with `FILE_PATTERNS = *.h` has said something true about its
    DOCUMENTATION target, and a consumer asking "why does the index hold more than the docs
    do" deserves that answer rather than silence.

    Empty, not the defaults, when nothing is declared — "not recorded" and "recorded as
    doxygen's default" are different claims and only the caller knows which it needs.

    @brief Read a target's declared FILE_PATTERNS.
    @return Declared patterns, or [].
    @version 1
    """
    return parse_doxyfile_values(doxyfile, "FILE_PATTERNS") or []


## Doxygen's own conventional locations for a project Doxyfile. NOT a target
## repo's convention — these are where doxygen users put it, so looking here is
## the same kind of default as the forced GENERATE_SQLITE3 flags.
_DOXYFILE_DIRS = ("docs", "doc")


## @brief Discover a repo's own Doxyfile (declaration-driven, never hardcoded).
## @param repo Repo root to search.
## @return Path to a Doxyfile at the repo root or a conventional docs dir, else None.
## @version 9
## @req REQ-DDB-INDEX-001
def discover_doxyfile(repo: Path) -> Path | None:
    """Look for `Doxyfile` at the repo root, then in doxygen's conventional
    `docs/`/`doc/` locations. Callers may always pass an explicit path instead;
    this is a convenience, not an assumption about layout.

    Lives here (not in the MCP layer) because BOTH entry points need it. It
    previously existed only in `mcp_server/state.py`, so the MCP server found a
    repo's Doxyfile while the CLI jumped straight to synthesis — the same repo
    built two ways produced materially different databases, silently dropping
    the repo's declared ALIASES / PREDEFINED / filters.

    REFUSES TO GUESS beyond those locations. It used to fall back to
    `sorted(repo.glob("*/Doxyfile"))[0]` — any subdirectory, resolved
    alphabetically. Dogfooding clew on itself caught what that does: it
    selected `sample/Doxyfile`, the demobot TEST FIXTURE, to index the whole
    project, and ran doxygen with cwd=sample/. The damage was masked because
    `--scope from-guard` replaces INPUT; under `--scope doxyfile` clew would
    have indexed the fixture instead of itself, silently, producing a
    well-formed database describing the wrong code.

    Measured across every codebase checked, that glob never once helped: the large
    C and C++ codebases have root Doxyfiles, one has none and correctly synthesizes,
    and the only repo where it fired was the one it got wrong. A wrong Doxyfile
    is worse than none, because none triggers synthesis from the declared scope.

    NOW A PURE QUERY — it no longer warns about the strays it declines (gh#4). It
    used to, and the advice it gave ("pass --doxyfile explicitly, or let the
    scope-derived Doxyfile be synthesized") became the SECOND of two messages once
    the CLI began reporting the same finding, so a user met one fact twice in one
    build. The strays are exposed by `rejected_doxyfile_candidates` and phrased by
    `describe_doxyfile_resolution`, which is the only place that knows what happens
    NEXT — and "what happens next" is the half that makes the finding actionable.

    Nothing lost by the removal, checked rather than assumed: `init._check_indexable`
    builds its own message from the return value, and the MCP build path captures the
    pipeline's log records into its result, so the CLI's sentence reaches a caller
    there too.

    @brief Find a repo's Doxyfile, refusing to guess among strays.
    @return The Doxyfile path, or None when none is found.
    @version 9
    """
    for candidate in (repo / "Doxyfile", *(repo / d / "Doxyfile" for d in _DOXYFILE_DIRS)):
        if candidate.is_file():
            return candidate
    return None


# The four situations Doxyfile resolution can land in (gh#4). They used to share
# ONE sentence, which described none of them: it named a path that was often the
# literal string "None", and it proposed `--doxyfile` to a user whose only way of
# reaching it was to have passed `--doxyfile` already.
#
# Two are supported routes that proceed via synthesis, two are genuine refusals.
# Keeping that split explicit is the point — a supported configuration reported as
# an error costs the reader their next twenty minutes on the wrong hypothesis.
DOXYFILE_EXPLICIT_MISSING = "explicit_missing"
DOXYFILE_NO_TARGET = "no_target"
DOXYFILE_ABSENT = "absent"
DOXYFILE_REJECTED = "rejected"


## @brief One classified Doxyfile-resolution situation and the sentence for it.
## @version 1
class DoxyfileResolution:
    """What resolution found, said about it, and whether it can proceed.

    `is_error` is carried alongside the message rather than inferred by the caller
    from the kind, so the "this is supported, not a failure" claim travels WITH the
    text that makes it. A caller cannot log the reassuring sentence at ERROR.

    @brief Outcome of classifying Doxyfile resolution.
    @version 1
    """

    __slots__ = ("is_error", "kind", "message")

    ## @brief Store the classified kind, its message, and whether it is fatal.
    ## @version 1
    ## @dg_internal
    def __init__(self, kind: str, message: str, is_error: bool) -> None:
        self.kind = kind
        self.message = message
        self.is_error = is_error


## @brief Doxyfile candidates discovery found but declined to adopt.
## @param repo Repo root to search.
## @return Stray Doxyfiles outside the trusted locations, in sorted order.
## @version 1
## @req REQ-DDB-INDEX-001
def rejected_doxyfile_candidates(repo: Path) -> list[Path]:
    """The strays `discover_doxyfile` refuses to guess among, exposed separately so
    a message can say WHERE a Doxyfile was found without discovery having to adopt
    it. Splitting "what did you find" from "what will you use" is what lets the
    refusal keep its reasoning: previously the only record that anything had been
    found at all was a warning inside discovery, so the CLI's own error could not
    mention it.

    Deliberately NOT a behaviour change. `discover_doxyfile` still returns None for
    every path this lists — adopting one is the defect that put a test fixture's
    Doxyfile in charge of indexing a whole project.

    @brief List the Doxyfiles discovery declined to adopt.
    @return Sorted stray candidate paths.
    @version 1
    """
    trusted = {repo / "Doxyfile", *(repo / d / "Doxyfile" for d in _DOXYFILE_DIRS)}
    return [p for p in sorted(repo.glob("*/Doxyfile")) if p not in trusted]


## @brief Which of the four resolution situations applies.
## @param explicit The --doxyfile path the user passed, or None.
## @param repo_root The --repo-root that was searched, or None.
## @param candidates Doxyfiles found but not adopted.
## @return One of the DOXYFILE_* situation constants.
## @version 1
## @dg_internal
def _doxyfile_situation(
    explicit: Path | None,
    repo_root: Path | None,
    candidates: list[Path],
) -> str:
    """Deliberately NOT named `_classify*`. This repo already has three unrelated
    `_classify` functions plus a `_classify_doxygen_line`, and gh#26 records what
    that does to the index: name-based resolution collapses them into one node and
    then reports the UNION of their neighbours at `confidence: exact`. A distinct
    name is free; a fourth collision is not.

    @brief Pick the resolution situation.
    @return The applicable DOXYFILE_* constant.
    @version 1
    """
    if explicit is not None:
        return DOXYFILE_EXPLICIT_MISSING
    if repo_root is None:
        return DOXYFILE_NO_TARGET
    return DOXYFILE_REJECTED if candidates else DOXYFILE_ABSENT


## @brief Phrase the explicit-but-absent --doxyfile situation.
## @return The message naming the path tried and the flag that changes the outcome.
## @version 1
## @dg_internal
def _msg_explicit_missing(explicit: Path | None, _root: Path | None, _cands: list[Path]) -> str:
    """@brief Message for a --doxyfile path that is not on disk."""
    return (
        f"the --doxyfile you passed does not exist: {explicit}. Discovery was not "
        "attempted, because an explicit path overrides it. Check that path — or give "
        "--repo-root instead, since a repo with no usable Doxyfile is still "
        "indexable: one is synthesized from the repo's declared scope, or from the "
        "whole repo when it declares none."
    )


## @brief Phrase the no-flags-at-all situation.
## @return The message naming --repo-root as the missing input.
## @version 1
## @dg_internal
def _msg_no_target(_explicit: Path | None, _root: Path | None, _cands: list[Path]) -> str:
    """@brief Message for neither --doxyfile nor --repo-root."""
    return (
        "no target to index: neither --doxyfile nor --repo-root was given, so no "
        "directory was searched and there is no repo to synthesize a Doxyfile for. "
        "Give --repo-root <path> — a Doxyfile is optional, and a repo that ships "
        "none is a supported configuration."
    )


## @brief Phrase the found-but-not-trusted situation, carrying the refusal's reasoning.
## @return The message naming where candidates were found and why they were declined.
## @version 1
## @dg_internal
def _msg_rejected(_explicit: Path | None, repo_root: Path | None, candidates: list[Path]) -> str:
    """@brief Message for stray Doxyfiles discovery declined to adopt."""
    root = Path(repo_root) if repo_root is not None else None
    found = ", ".join(str(p.relative_to(root)) if root is not None else str(p) for p in candidates)
    return (
        f"found {found} under {root}, but NOT in a location a project Doxyfile is "
        f"trusted from (the repo root, or {'/'.join(_DOXYFILE_DIRS)}), so it was not "
        "adopted and a Doxyfile is being synthesized instead. This is a refusal to "
        "GUESS, not a failure to look: picking a stray alphabetically once selected a "
        "test fixture's Doxyfile to index a whole project, and a wrong Doxyfile is "
        "worse than none because none triggers synthesis. Pass --doxyfile <path> to "
        "select one deliberately."
    )


## @brief Phrase the genuinely-Doxyfile-less situation as the supported path it is.
## @return The message stating synthesis will be used.
## @version 1
## @dg_internal
def _msg_absent(_explicit: Path | None, repo_root: Path | None, _cands: list[Path]) -> str:
    """@brief Message for a repo that ships no Doxyfile."""
    return (
        f"{repo_root} ships no Doxyfile. This is a SUPPORTED configuration, not an "
        "error: one is being synthesized from the repo's declared scope, or from the "
        "whole repo when it declares none. Pass --doxyfile <path> only to use a "
        "specific one — a repo's own Doxyfile is its DOCUMENTATION scope and may "
        "cover far less than you want indexed."
    )


# Situation → sentence, and the subset that cannot proceed. One table so a new
# situation cannot be added with a message and no severity (or the reverse), which
# is the drift that let one sentence serve four cases in the first place.
_DOXYFILE_MESSAGES = {
    DOXYFILE_EXPLICIT_MISSING: _msg_explicit_missing,
    DOXYFILE_NO_TARGET: _msg_no_target,
    DOXYFILE_REJECTED: _msg_rejected,
    DOXYFILE_ABSENT: _msg_absent,
}

_DOXYFILE_FATAL_SITUATIONS = frozenset({DOXYFILE_EXPLICIT_MISSING, DOXYFILE_NO_TARGET})


## @brief Classify a Doxyfile-resolution outcome and phrase it (gh#4).
## @param explicit The --doxyfile path the user passed, or None.
## @param repo_root The --repo-root that was searched, or None when none was given.
## @param candidates Doxyfiles found but not adopted (see rejected_doxyfile_candidates).
## @return The classified situation, its message, and whether it is fatal.
## @version 1
## @req REQ-DDB-INDEX-001
def describe_doxyfile_resolution(
    explicit: Path | None,
    repo_root: Path | None,
    candidates: list[Path],
) -> DoxyfileResolution:
    """Say what was looked for, where, what was found, and the ONE action that
    changes the outcome — and never propose an action already taken.

    The situations, in the order they are distinguished:

    - `explicit_missing` — a `--doxyfile` was passed and is not on disk. FATAL, and
      the one case the old text got actively wrong: it answered "Pass --doxyfile".
      The action that changes the outcome is `--repo-root`, because a repo with no
      usable Doxyfile is still indexable by synthesis.
    - `no_target` — neither flag. FATAL, and "Doxyfile not found" was not even true:
      no directory was ever searched. The old text rendered the absent path as the
      literal string "None".
    - `rejected` — a repo was searched and Doxyfiles were found outside the trusted
      locations. NOT fatal; synthesis proceeds. The message carries the reasoning,
      because discovery refuses to guess among strays for a measured reason — it was
      once caught selecting a test fixture's Doxyfile to index a whole project — and
      a bare "not used" invites the reader to conclude the tool failed to find what
      it plainly did find.
    - `absent` — a repo was searched and genuinely ships none. NOT fatal, and this
      is the bullet gh#4 leads with: a SUPPORTED configuration that the tool handles
      well and used to greet with an error.

    @brief Classify and phrase a Doxyfile-resolution outcome.
    @return The situation, its sentence, and its severity.
    @version 1
    """
    kind = _doxyfile_situation(explicit, repo_root, candidates)
    message = _DOXYFILE_MESSAGES[kind](explicit, repo_root, candidates)
    return DoxyfileResolution(kind, message, kind in _DOXYFILE_FATAL_SITUATIONS)


## @brief Synthesize a minimal Doxyfile for a repo that has none.
## @param repo_root The repository whose name labels the project and is stripped from stored paths.
## @param output_dir Absolute directory doxygen writes sqlite3/xml into (becomes OUTPUT_DIRECTORY); the Doxyfile is written here too, so its parent is a valid work_dir.
## @return Path to the written Doxyfile.
## @version 5
## @req REQ-DDB-INDEX-001
def synthesize_doxyfile(repo_root: Path, output_dir: Path) -> Path:
    """Write the smallest Doxyfile that lets the pipeline run: PROJECT_NAME, an
    ABSOLUTE OUTPUT_DIRECTORY, STRIP_FROM_PATH, and an empty INPUT. Everything
    else the pipeline needs — GENERATE_SQLITE3, EXTRACT_ALL, RECURSIVE, ...
    — is appended by `_build_doxyfile_content`'s forced flags, and the actual
    INPUT comes from the resolved scope via `replace_input`. This lets clew
    index a repo that ships no Doxyfile — over its declared `index_scope:` roots, or
    over the whole repository when it declares nothing — deriving the whole build
    from declarations, per the no-hardcoding mandate.

    STRIP_FROM_PATH IS NOT COSMETIC, and its absence was a privacy defect. The
    pipeline's contract is that `path.name` holds a REPO-ROOT-RELATIVE path —
    that is the whole reason `fix_doxygen_paths` exists. On this path the
    contract was broken three ways at once: nothing set STRIP_FROM_PATH,
    `replace_input` feeds doxygen ABSOLUTE resolved INPUT paths so it stored
    absolute names, and `fix_doxygen_paths` then returned early precisely because
    STRIP_FROM_PATH was unset. Measured on this repo's own self-index: 112 of 112
    rows absolute, every one carrying the builder's home directory. `list_files`
    publishes that column over MCP, so a synthesized index disclosed the build
    machine's directory layout to any consumer of a shared db.

    It survived because it FAILS SILENTLY UPWARD: `Path(repo_root) / "/abs/p"`
    returns the absolute operand, so every downstream reader resolved correctly
    and no test could notice.

    **This docstring used to continue "Only the repo-supplied-Doxyfile path
    produced relative names." That was FALSE, and saying it is why nobody looked
    there for two more weeks.** A repo whose own STRIP_FROM_PATH covers part of its
    tree keeps absolute names for the rest — measured on a real C++ target: 145 of
    474 rows, plus 32 directory rows the fix did not even scan. `fix_doxygen_paths`
    now enforces the repo-root-relative contract as a POST-CONDITION on every row,
    which is where the guarantee belongs.

    Set only in the SYNTHESIZED Doxyfile, never in the forced flags: a repo that
    ships its own Doxyfile owns its STRIP_FROM_PATH, and overriding it would both
    discard a declaration and defeat `fix_doxygen_paths`' reconstruction. We
    dictate policy only where we are the author — and enforce our own contract
    afterwards regardless of whose declaration produced the input.

    @brief Write a minimal Doxyfile driven by the derived scope.
    @version 5
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    doxyfile = output_dir / "Doxyfile.synth"
    doxyfile.write_text(
        f"PROJECT_NAME = {repo_root.name}\n"
        f"OUTPUT_DIRECTORY = {output_dir}\n"
        f"STRIP_FROM_PATH = {repo_root.resolve()}\n"
        "INPUT =\n",
        encoding="utf-8",
    )
    logger.info("synthesized a Doxyfile (repo declares scope but ships none): %s", doxyfile)
    return doxyfile


## @brief Build the augmented Doxyfile content piped to doxygen on stdin.
## @version 11
## @req REQ-DDB-INDEX-001
def _build_doxyfile_content(
    doxyfile: Path,
    extra_input: list[str] | None,
    extra_exclude: list[str] | None,
    replace_input: bool = False,
    output_dir: Path | None = None,
    predefined: str = "",
) -> str:
    """Build the augmented Doxyfile content piped to doxygen on stdin.

    Forces SQLite/XML/EXTRACT_ALL flags. `extra_exclude` always applies:
    without `extra_input` it is APPENDED to the repo's own EXCLUDE (so
    `--extra-exclude` works standalone to trim scope); with `extra_input` the
    EXCLUDE list is first CLEARED then re-applied, so submodule source added via
    `extra_input` isn't silently dropped by the repo's own EXCLUDE.

    `replace_input` additionally CLEARS the Doxyfile's own INPUT list, so the
    supplied roots become the whole scope. That is what a declaration-derived
    scope (`--scope from-guard`) needs: the Doxyfile's INPUT is a different,
    independently-written statement of scope, and silently unioning the two
    would re-admit exactly the trees the repo's declaration leaves out.

    `predefined` is pre-rendered Doxyfile text from `preprocessor.doxyfile_lines`
    (gh#17) — the declared PREPROCESSOR CONFIGURATION this index represents. It is
    appended AFTER the repo's own Doxyfile text and as `PREDEFINED +=`, never `=`,
    so a target that already declares its own PREDEFINED keeps it and gains ours.
    A target declaring nothing passes `""`, and the content is byte-identical to
    what this function produced before gh#17.

    Rendering happens in `preprocessor.py` rather than here, and passing TEXT
    rather than a macro list is deliberate: this string is what
    `doxyfile_content_for` hashes for the index cache, so there is exactly one
    place that decides what doxygen sees and no way for the hashed form and the
    piped form to drift.
    """
    ## `predefined` COMES FROM THE TARGET REPO'S `.clew.yaml` and lands AFTER the forced
    ## block, so anything it smuggles wins over every line above. `_declared_macros` applies
    ## only `str(v).strip()`, so an interior newline survives and a trailing `#` defeats the
    ## quoting — the same line-based injection as a path, through a different door. Filtered
    ## here because this is the single choke point every source passes through.
    content = doxyfile.read_text() + _DOXYFILE_FORCED_FLAGS + _safe_predefined(predefined)
    if output_dir is not None:
        # Forced LAST so it wins over the repo's own OUTPUT_DIRECTORY (doxygen
        # takes the final assignment). Absolute, so it is independent of cwd —
        # which must stay the repo root for relative INPUT paths to resolve.
        content += f"OUTPUT_DIRECTORY = {Path(output_dir).resolve()}\n"
    # The SAME rule `treescan.doxygen_input_roots` mirrors when it enumerates the
    # tree for the index cache, asked of one shared predicate rather than
    # re-derived here (gh#3). The two were identical and free to drift, and the
    # only symptom of drift would have been a cache that hashes a different file
    # set than doxygen reads.
    from .treescan import extra_input_clears_exclude

    if not extra_input_clears_exclude(extra_input):
        # --extra-exclude still applies standalone: append to the repo's own
        # EXCLUDE (no clear — with no extra_input there is no submodule source
        # to un-hide). Previously this early-returned, silently dropping it.
        for path in extra_exclude or []:
            content += f"EXCLUDE += {path}\n"
        return content
    if replace_input:
        content += "INPUT =\n"
        ## AND `EXCLUDE_PATTERNS`, which is the GLOB spelling of the same decision
        ## (gh#333). Clearing `EXCLUDE` below and leaving this standing was arbitrary,
        ## and it silently defeated the whole scope change on the target it was built
        ## for: entropic declares `EXCLUDE_PATTERNS = */extern/* */build/* */tests/*`,
        ## so its llama.cpp submodule was admitted to INPUT and then dropped again —
        ## a build that indexed 16 vendored files, reported success, and looked like a
        ## working measurement.
        ##
        ## Only under `replace_input`, i.e. only when the operator asked for the
        ## repo's own scope statement to be replaced. A plain `--extra-exclude` build
        ## leaves both keys exactly as the repo wrote them.
        content += "EXCLUDE_PATTERNS =\n"
    for path in _inlineable(list(extra_input), "INPUT"):
        content += f"INPUT += {path}\n"
    content += "EXCLUDE =\n"
    if extra_exclude:
        for path in _inlineable(list(extra_exclude), "EXCLUDE"):
            content += f"EXCLUDE += {path}\n"
    logger.info(
        "Appending %d extra INPUT entries (EXCLUDE cleared, %d re-excluded)",
        len(extra_input),
        len(extra_exclude) if extra_exclude else 0,
    )
    return content


## @brief Drop paths that cannot be written as a Doxyfile value.
## @param paths Candidate INPUT/EXCLUDE entries.
## @param kind Which key they are destined for, for the warning.
## @return The paths safe to inline, in order.
## @version 1
## @dg_internal
def _inlineable(paths: list[str], kind: str) -> list[str]:
    """DOXYGEN'S CONFIG IS LINE-BASED, so a path containing a newline TERMINATES the
    assignment and everything after it becomes a new directive. POSIX allows every byte
    except NUL and `/` in a filename and git stores it faithfully, so a hostile repository
    can ship `a.c\nINPUT_FILTER = /bin/sh -c ...` as a BASENAME and obtain arbitrary command
    execution from indexing alone.

    Verified by rendering the configuration: the tail arrived as its own `INPUT_FILTER`
    directive, positioned after the forced flags and therefore winning over them.

    SKIPPED RATHER THAN REFUSED, and that is not leniency. Doxygen's format cannot
    REPRESENT such a path, so the file was never indexable by any means — skipping loses
    nothing that was achievable, while refusing the whole build would make one pathological
    filename render an entire repository unindexable. The skip is logged as a WARNING with a
    count, because an accepted-but-unread entry is this project's most repeated defect.

    Carriage return and NUL are rejected on the same reasoning; a bare `\r` can terminate a
    line for some parsers and NUL cannot appear in a path at all.

    @brief Filter out paths that would inject a Doxyfile directive.
    @return The safe subset.
    @version 1
    """
    safe = [p for p in paths if not any(c in p for c in "\n\r\x00")]
    dropped = len(paths) - len(safe)
    if dropped:
        logger.warning(
            "%s: skipping %d path(s) containing a control character. A newline in a path "
            "would terminate the Doxyfile assignment and turn the remainder into a "
            "directive, and doxygen cannot represent such a path in any case.",
            kind,
            dropped,
        )
    return safe


## @brief Strip any line from a declared PREDEFINED block that is not a macro definition.
## @param predefined Pre-rendered `PREDEFINED +=` text from the target's declaration.
## @return The same text with injected directive lines removed.
## @version 1
## @dg_internal
def _safe_predefined(predefined: str) -> str:
    """A `PREDEFINED` block is a sequence of `PREDEFINED += ...` continuation lines and nothing
    else. Any line that instead assigns some OTHER doxygen key got there by injection: the
    declaration parser applies only `str(v).strip()`, so an interior newline in a declared
    macro survives into this text and becomes a directive that overrides the forced block above
    it. Verified end to end against doxygen 1.9.8 — an injected `INPUT_FILTER` ran.

    Keeping only the lines that look like part of the block, rather than blacklisting keys, is
    what makes this hold for a key nobody has thought of yet.

    @brief Drop non-macro lines from a declared PREDEFINED block.
    @return The filtered text.
    @version 1
    """
    kept, dropped = [], 0
    for line in predefined.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("PREDEFINED") or stripped.startswith("\\"):
            kept.append(line)
        elif "=" in stripped and not stripped.split("=", 1)[0].strip().isupper():
            kept.append(line)
        else:
            dropped += 1
    if dropped:
        logger.warning(
            "preprocessor: dropped %d declared PREDEFINED line(s) that assigned a doxygen "
            "option rather than defining a macro. A newline inside a declared macro becomes a "
            "directive that overrides the forced configuration.",
            dropped,
        )
    return "\n".join(kept) + ("\n" if kept else "")


## @brief Bucket a doxygen-stdout line: warning, file, phase, or other.
## @version 1
## @return One of "warning", "file", "phase", or "other" classifying the line.
## @dg_internal
def _classify_doxygen_line(line: str) -> str:
    """Bucket a doxygen-stdout line: warning, file, phase, or other."""
    lower = line.lower()
    if "warning:" in lower or "error:" in lower:
        return "warning"
    if line.startswith(_DOXY_FILE_PREFIXES):
        return "file"
    return "phase" if line.startswith(_DOXY_PHASE_PREFIXES) else "other"


## @brief Feed the generated Doxyfile to doxygen's stdin, from a thread.
## @param proc The running doxygen process.
## @param content The complete generated Doxyfile text.
## @return None.
## @version 1
## @dg_internal
def _write_doxyfile_stdin(proc: subprocess.Popen, content: str) -> None:
    """RUNS ON A THREAD SO BOTH PIPES ARE SERVICED AT ONCE. Writing the config from the main
    thread and only then reading stdout deadlocks whenever the config exceeds the pipe buffer and
    doxygen emits output before consuming all of it — measured at 356 KB of config against a
    64 KiB buffer, and observed in the field as a hung MCP call.

    SWALLOWS ITS ERRORS ON PURPOSE. If doxygen dies early the write fails with EPIPE, and that is
    not the interesting failure: the reader will see the closed stdout and `proc.wait()` will
    report the real exit code. Raising here would replace a useful diagnostic with a traceback
    from a daemon thread that nobody joins on the error path.

    @brief Write the config to stdin and close it.
    @return None.
    @version 1
    """
    try:
        if proc.stdin is not None:
            proc.stdin.write(content)
            proc.stdin.close()
    except (BrokenPipeError, OSError, ValueError):
        pass


## @brief Drive a progress bar from doxygen's stdout.
## @version 1
## @return Tuple of (total warning/error count, up to the first 3 warning lines).
## @dg_internal
def _consume_doxygen_output(proc: subprocess.Popen) -> tuple[int, list[str]]:
    """Drive a progress bar from doxygen's stdout. Return (warn_count, first_warnings)."""
    warn_count = 0
    file_count = 0
    first_warnings: list[str] = []
    assert proc.stdout is not None
    with make_progress(known_total=False) as progress:
        task = progress.add_task("doxygen", total=None)
        for raw in proc.stdout:
            line = raw.rstrip()
            if not line:
                continue
            kind = _classify_doxygen_line(line)
            if kind == "warning":
                warn_count += 1
                if len(first_warnings) < 3:
                    first_warnings.append(line)
            elif kind == "file":
                file_count += 1
                progress.update(task, completed=file_count)
            elif kind == "phase":
                progress.update(
                    task,
                    description=f"doxygen: {line[:30].lower()}",
                )
    return warn_count, first_warnings


## @brief Print first warnings + count of any suppressed.
## @version 2
## @dg_internal
def _surface_doxygen_warnings(warn_count: int, first_warnings: list[str]) -> None:
    """Print first warnings + count of any suppressed, onto whichever console is
    active — this is one of the two writers in the build path that renders outside
    `make_progress`, so it has to honour the same seam."""
    out = active_console()
    for w in first_warnings:
        line = w.split("\n", 1)[0]
        out.print(
            f"  [dim yellow]⚠ {line}[/]",
            overflow="ellipsis",
            no_wrap=True,
        )
    if warn_count > len(first_warnings):
        out.print(
            f"  [dim yellow]⚠ ({warn_count - len(first_warnings)} more warnings suppressed)[/]",
        )


## @brief Extract a value from a Doxyfile by key.
## @version 2
## @return The trimmed value string for the key, or "" if the key is not present.
## @req REQ-DDB-INDEX-001
def parse_doxyfile_value(doxyfile: Path, key: str) -> str:
    """Extract a value from a Doxyfile by key.

    @brief Parse a single key=value from a Doxyfile.
    @version 3
    """
    for line in doxyfile.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith(key) and "=" in stripped:
            return stripped.split("=", 1)[1].strip()
    return ""


## @brief Collect every value assigned to a Doxyfile key, across = / += / continuations.
## @return Whitespace-split values for the key, in file order.
## @version 1
## @req REQ-DDB-INDEX-001
def parse_doxyfile_values(doxyfile: Path, key: str) -> list[str]:
    """Doxyfile lists (INPUT, EXCLUDE) may be split over `=` plus any number
    of `+=` lines and backslash continuations. `parse_doxyfile_value` returns
    only the first line's text, which is fine for scalars but loses list
    entries — this collects them all, for the incremental cache's file
    enumeration.

    @brief Parse a whole Doxyfile list value.
    @version 1
    """
    values: list[str] = []
    collecting = False
    for raw in doxyfile.read_text().splitlines():
        line = raw.strip()
        continues = line.endswith("\\")
        body = line[:-1].strip() if continues else line
        if not collecting:
            if not (body.startswith(key) and "=" in body):
                continue
            lhs, rhs = body.split("=", 1)
            if lhs.strip().rstrip("+") != key:
                continue
            values.extend(rhs.split())
        else:
            values.extend(body.split())
        collecting = continues
    return values


## @brief The exact Doxyfile text the pipeline pipes to doxygen.
## @return Augmented Doxyfile content (forced flags + PREDEFINED + extra INPUT/EXCLUDE).
## @version 4
## @req REQ-DDB-INDEX-001
def doxyfile_content_for(
    doxyfile: Path,
    extra_input: list[str] | None = None,
    extra_exclude: list[str] | None = None,
    replace_input: bool = False,
    predefined: str = "",
) -> str:
    """Public wrapper over `_build_doxyfile_content` so the incremental index
    cache can hash EXACTLY what doxygen will be fed (Doxyfile bytes + forced
    flags + PREDEFINED + extra INPUT/EXCLUDE lines) when computing its tree hash.

    `predefined` MUST be threaded through here and not only into `run_doxygen`
    (gh#17). The cache's whole claim is "this tree and this Doxyfile text are
    unchanged, so the previous doxygen output is still valid" — and a changed
    `preprocessor:` declaration changes neither a source file nor the target's
    Doxyfile. Omitted from the hash, editing the declared macro list would serve
    the PREVIOUS configuration's parse from cache and report success: a
    well-formed index of a variant the owner just stopped declaring. That is the
    silent-wrong-answer class this repo keeps finding, so it is pinned by a test.

    @brief Expose the augmented Doxyfile content for hashing.
    @version 4
    """
    return _build_doxyfile_content(
        doxyfile, extra_input, extra_exclude, replace_input, None, predefined
    )


## @brief The doxygen output directory actually in effect for a build.
## @param doxyfile Target repo's Doxyfile.
## @param work_dir Directory doxygen runs in (relative OUTPUT_DIRECTORY is relative to it).
## @param output_dir Absolute override forced by the pipeline, or None to honor the Doxyfile.
## @return Resolved output directory.
## @version 4
## @req REQ-DDB-INDEX-001
def effective_output_dir(doxyfile: Path, work_dir: Path, output_dir: Path | None = None) -> Path:
    """clew is a READ-ONLY consumer of target repos, so it forces its own
    OUTPUT_DIRECTORY rather than honoring the Doxyfile's. Honoring it wrote
    doxygen's sqlite3/xml output straight into the target working tree (a repo
    declares `docs/generated/doxygen`), which mutates a repo the operator may
    be mid-edit in, collides between concurrent builds of the same repo, and
    silently shares a directory with that repo's OWN doxygen output.

    Honoring a repo's declared INPUT/ALIASES/PREDEFINED while overriding where
    output lands is the right split: the declaration says WHAT to index, not
    where clew should put its artifacts.

    @brief Resolve the effective doxygen output directory.
    @return The forced directory when given, else the Doxyfile's.
    @version 3
    """
    if output_dir is not None:
        return Path(output_dir).resolve()
    base_dir = parse_doxyfile_value(doxyfile, "OUTPUT_DIRECTORY") or "."
    return (work_dir / base_dir).resolve()


## @brief Resolve where doxygen writes its SQLite output for this build.
## @param doxyfile Target repo's Doxyfile.
## @param work_dir Directory doxygen runs in.
## @param output_dir Absolute override forced by the pipeline, or None.
## @return Path to doxygen_sqlite3.db.
## @version 2
## @req REQ-DDB-INDEX-001
def doxygen_db_path(doxyfile: Path, work_dir: Path, output_dir: Path | None = None) -> Path:
    """Doxygen puts sqlite3 output in <OUTPUT_DIRECTORY>/sqlite3/ by default,
    or <OUTPUT_DIRECTORY>/<SQLITE3_OUTPUT>/ when that key is set.

    @brief Locate the doxygen SQLite output path.
    @version 2
    """
    sqlite_subdir = parse_doxyfile_value(doxyfile, "SQLITE3_OUTPUT") or "sqlite3"
    return (
        effective_output_dir(doxyfile, work_dir, output_dir) / sqlite_subdir / "doxygen_sqlite3.db"
    )


##
# @brief Whether the doxygen on PATH was BUILT with sqlite3 output support.
# @param binary Doxygen executable to probe; defaults to whatever is on PATH.
# @return True when the binary implements GENERATE_SQLITE3, False when it does not.
# @version 1
# @req REQ-DDB-CLI-002
def doxygen_supports_sqlite3(binary: str = "doxygen") -> bool | None:
    """A BUILD-TIME OPTION, NOT A VERSION. doxygen's sqlite3 generator is gated behind
    `-Dbuild_sqlite3=ON`, and Ubuntu ships it OFF — so `apt install doxygen` on 22.04 yields
    1.9.1 with no sqlite3 support, and upgrading the version does not necessarily fix it.
    Every stock 22.04 user hits this (gh#3).

    THE SYMPTOM IS SEVERAL LAYERS FROM THE CAUSE, which is why this exists. An unsupported
    tag is IGNORED rather than refused: doxygen warns "ignoring unsupported tag
    'GENERATE_SQLITE3'", buries it among thousands of suppressed warnings, exits ZERO, and
    writes no database. The pipeline then reports "Expected database not found: <path>",
    naming neither doxygen nor sqlite3 nor anything actionable.

    PROBED FROM THE BINARY'S OWN CONFIG TEMPLATE. `doxygen -g -` writes a default Doxyfile to
    stdout listing every tag the binary implements, so the tag's ABSENCE there is the binary
    telling us it cannot do this. Measured: 4 occurrences on a 1.9.8 build with support, 0 on
    Ubuntu's 1.9.1 without it. Parsing `--version` would be wrong — the same version number
    exists both ways.

    RETURNS None WHEN THE PROBE ITSELF COULD NOT RUN, never False. A missing binary or a
    timeout is not evidence of missing support, and reporting it as such would send someone
    rebuilding doxygen to fix a PATH problem.

    @brief Probe whether doxygen implements GENERATE_SQLITE3.
    @return True/False, or None when the probe could not be run.
    @version 1
    """
    if shutil.which(binary) is None:
        return None
    try:
        proc = subprocess.run(
            [binary, "-g", "-"],
            capture_output=True,
            text=True,
            timeout=30,
            env=clean_subprocess_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return "GENERATE_SQLITE3" in proc.stdout


## @brief Run doxygen with GENERATE_SQLITE3 and return the database path.
## @version 10
## @req REQ-DDB-INDEX-001
def run_doxygen(
    doxyfile: Path,
    work_dir: Path,
    extra_input: list[str] | None = None,
    extra_exclude: list[str] | None = None,
    replace_input: bool = False,
    output_dir: Path | None = None,
    predefined: str = "",
) -> Path:
    """Run doxygen with GENERATE_SQLITE3 and return the database path.

    output_dir: force where doxygen writes, overriding the Doxyfile's own
    OUTPUT_DIRECTORY. The pipeline always passes one so a build never writes
    into the target repo (see effective_output_dir).

    extra_input: additional INPUT paths appended to the Doxyfile. Useful
    for pulling in submodule source that isn't in the repo's baseline
    INPUT list. With EXTRACT_ALL=YES doxygen creates memberdef rows
    for these files even when they lack doxygen-formatted docstrings.

    replace_input: make extra_input the WHOLE INPUT list (the Doxyfile's own
    INPUT is cleared) — used by the declaration-derived scope.

    predefined: pre-rendered `PREDEFINED +=` Doxyfile text for the declared
    preprocessor configuration (gh#17). Empty for a target that declares none, in
    which case doxygen is fed exactly what it was fed before that change.

    REFUSES BEFORE SPAWNING when the binary is absent, because `subprocess.Popen`
    on a missing executable raises a FileNotFoundError naming `'doxygen'` from
    twelve frames deep — which reads as a clew crash rather than a missing
    prerequisite. Checked HERE rather than in the CLI because this function is the
    single choke point both entry points pass through, so the CLI and the MCP
    server get the same refusal without either restating it.

    @brief Run doxygen and return path to generated sqlite3 database.
    @raises DoxygenUnavailableError When the doxygen binary is not on PATH.
    @version 10
    """
    if shutil.which("doxygen") is None:
        raise DoxygenUnavailableError(
            "the 'doxygen' binary is not on PATH, and it is the one prerequisite "
            "that cannot be installed from PyPI (it is a system package).\n"
            "  Debian/Ubuntu:  sudo apt install doxygen\n"
            "  macOS:          brew install doxygen\n"
            "  Fedora:         sudo dnf install doxygen\n"
            "Then re-run this build. 'clew init' also checks for it."
        )
    logger.info("Running doxygen: %s (cwd: %s)", doxyfile, work_dir)
    doxyfile_content = _build_doxyfile_content(
        doxyfile,
        extra_input,
        extra_exclude,
        replace_input,
        output_dir,
        predefined,
    )
    proc = subprocess.Popen(
        ["doxygen", "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(work_dir),
        text=True,
        bufsize=1,
        env=clean_subprocess_env(),
    )
    assert proc.stdin is not None and proc.stdout is not None
    ## STDIN IS WRITTEN ON A THREAD, AND THAT IS A DEADLOCK FIX RATHER THAN A TIDY-UP.
    ##
    ## This used to be `write(...)` then `close()` then read stdout — nobody read stdout until the
    ## WHOLE config had been written. Both pipes have a ~64 KiB OS buffer, and the config is not
    ## small: clew writes explicit file lists into INPUT, so it scales with the repo.
    ## MEASURED: 356,077 bytes for a 4,878-file INPUT — 5.4x the buffer. doxygen emits
    ## config-parse warnings while it is still reading, so its stdout fills, it blocks on write,
    ## we block on write, and neither side can ever proceed. Reproduced with this exact spawn
    ## shape: hung until killed.
    ##
    ## Observed in the field as a single MCP call hanging with no concurrency at all, which is
    ## what ruled out the concurrent-build theory this was first attributed to.
    ##
    ## `communicate()` is the textbook fix and is NOT used here, deliberately: it buffers stdout
    ## and would delete the live progress bar `_consume_doxygen_output` drives off the stream, on
    ## a stage that routinely runs for seconds. A writer thread fixes the deadlock and keeps the
    ## bar — both pipes are serviced at once, which is the actual requirement.
    writer = threading.Thread(
        target=_write_doxyfile_stdin, args=(proc, doxyfile_content), daemon=True
    )
    writer.start()
    warn_count, first_warnings = _consume_doxygen_output(proc)
    ## BOUNDED, because an unbounded wait here is the second half of the same incident: the MCP
    ## server holds its per-target build lock across this call, so one stalled doxygen makes every
    ## later stale query in that process queue forever. The value is a BACKSTOP, not a budget — no
    ## legitimate build approaches it, and the point is that a wedged one ends.
    try:
        rc = proc.wait(timeout=_DOXYGEN_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        logger.error(
            "doxygen did not finish within %d s and was killed. The index was NOT updated; the "
            "previous one is untouched, because the build stages into a temp file and only "
            "swaps on success.",
            _DOXYGEN_TIMEOUT,
        )
        sys.exit(1)
    writer.join(timeout=5)
    _surface_doxygen_warnings(warn_count, first_warnings)
    if rc != 0:
        logger.error("Doxygen exited with code %d", rc)
        sys.exit(1)

    db_path = doxygen_db_path(doxyfile, work_dir, output_dir)
    if not db_path.exists():
        ## NAME THE CAUSE, NOT THE MISSING FILE (gh#3). doxygen exits ZERO when it does not
        ## implement GENERATE_SQLITE3 — it warns that the tag is unsupported, buries that among
        ## thousands of suppressed warnings, and writes nothing. So the first observable symptom
        ## is an absent database, and reporting only the path sends the reader looking for a
        ## permissions or disk problem in the one case where the binary is simply incapable.
        ##
        ## Probed HERE rather than trusted from the doctor: `clew init` is optional, the MCP
        ## build path never runs it, and a machine can change under a long-lived install.
        if doxygen_supports_sqlite3() is False:
            logger.error(
                "doxygen was built WITHOUT sqlite3 support, so it ignored GENERATE_SQLITE3 and "
                "wrote no database. This is a build option (-Dbuild_sqlite3=ON), not a version — "
                "Ubuntu 22.04's doxygen 1.9.1 lacks it. Install a build that has it, then "
                "confirm with: doxygen -g - | grep GENERATE_SQLITE3"
            )
        else:
            logger.error("Expected database not found: %s", db_path)
        sys.exit(1)
    return db_path


## @brief Copy the generated database to the target location.
## @version 1
## @req REQ-DDB-INDEX-001
def copy_database(src: Path, dest: Path) -> None:
    """Copy the generated database to the target location.

    @brief Copy database to output location.
    @version 1
    """
    # mode=0o700 — the docs DB is built per-user from per-user repo state;
    # restrict the parent dir (typically `.explorer/`) to the owner.
    dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    shutil.copy2(str(src), str(dest))
    logger.info("Copied database to: %s", dest)


# doxygen writes descriptions straight from source comments into its sqlite3
# output; a non-UTF-8 source comment (latin-1/GBK/etc.) lands as raw invalid
# bytes in these free-text columns. The docs server already decodes with
# errors="replace" on read, but sanitizing at build time keeps the shipped
# index clean and every downstream augmentation step honest.
_SANITIZE_TARGETS = (
    ("memberdef", ("briefdescription", "detaileddescription")),
    ("compounddef", ("briefdescription", "detaileddescription")),
)


## @brief Repair one text column's invalid-UTF-8 rows; return the count fixed.
## @version 2
## @return Number of rows in table.col whose invalid UTF-8 bytes were replaced.
## @dg_internal
def _repair_utf8_column(conn: sqlite3.Connection, table: str, col: str) -> int:
    """UPDATE rows of `table.col` whose bytes aren't valid UTF-8 to the
    errors='replace' form. Reads under text_factory=bytes."""
    rows = conn.execute(f"SELECT rowid, {col} FROM {table} WHERE {col} IS NOT NULL").fetchall()
    fixes = []
    for rowid, val in rows:
        if not isinstance(val, bytes):
            continue
        try:
            val.decode("utf-8")
        except UnicodeDecodeError:
            fixes.append((val.decode("utf-8", errors="replace"), rowid))
    conn.executemany(
        f"UPDATE {table} SET {col} = ? WHERE rowid = ?",
        fixes,
    )
    return len(fixes)


## @brief Sanitize non-UTF-8 bytes doxygen wrote into description columns.
## @version 1
## @return Total number of description rows repaired across all target columns.
## @req REQ-DDB-INDEX-001
def sanitize_doxygen_text(db_path: Path) -> int:
    """Repair invalid-UTF-8 description text in the doxygen sqlite output.

    Runs right after doxygen generates the db (before augmentation) so every
    downstream step and the shipped index see clean UTF-8. Returns rows fixed.

    @brief Repair non-UTF-8 description columns in the doxygen sqlite db.
    @version 1
    """
    conn = sqlite3.connect(str(db_path))
    conn.text_factory = bytes  # raw bytes so invalid UTF-8 is detectable
    try:
        fixed = sum(
            _repair_utf8_column(conn, table, col)
            for table, cols in _SANITIZE_TARGETS
            for col in cols
        )
        conn.commit()
    finally:
        conn.close()
    if fixed:
        logger.info("Sanitized %d non-UTF-8 description row(s)", fixed)
    return fixed


## @brief Find the real function name at a body span via tree-sitter.
## @utility
## @version 2
def _real_function_name_at(
    repo_root: Path, rel: str, bstart: int, cache: dict, parser, language
) -> str | None:
    from .call_edges import _ast_parse_one_file
    from .callback_edges import _innermost_identifier

    parsed = _ast_parse_one_file(rel, repo_root / rel, cache, parser, language)
    if parsed is None:
        return None
    tree, _ = parsed
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == "function_definition":
            r0, r1 = node.start_point[0] + 1, node.end_point[0] + 1
            if r0 <= bstart <= r1:
                decl = node.child_by_field_name("declarator")
                ident = _innermost_identifier(decl) if decl is not None else None
                if ident is not None:
                    return ident.text.decode("utf-8", errors="replace")
        stack.extend(node.children)
    return None


## @brief Merge a repaired __attribute__ def-row into an existing decl row, or rename.
##
## Doxygen splits a `__attribute__((...))`-decorated function into a bodyless
## declaration row (correct name) + a body-owning row misnamed
## `__attribute__`. Simply renaming the body row would leave TWO same-named
## rows and split the call edges across them (regressing the call tree). So:
## if a bodyless declaration row with the real name exists in the same file,
## transfer the body span onto it and DELETE the __attribute__ row (one row,
## all edges resolve to it); otherwise just rename. Returns True on merge or
## rename.
## @utility
## @version 1
def _repair_one_attribute_row(
    conn: sqlite3.Connection,
    rowid: int,
    bstart: int,
    bend: int,
    file_id: int,
    real: str,
) -> bool:
    decl = conn.execute(
        "SELECT rowid FROM memberdef WHERE name = ? AND kind = 'function' "
        "AND file_id = ? AND (bodystart IS NULL OR bodystart <= 0) LIMIT 1",
        (real, file_id),
    ).fetchone()
    if decl is not None:
        conn.execute(
            "UPDATE memberdef SET bodystart = ?, bodyend = ?, bodyfile_id = ? WHERE rowid = ?",
            (bstart, bend, file_id, decl[0]),
        )
        conn.execute("DELETE FROM memberdef WHERE rowid = ?", (rowid,))
    else:
        conn.execute("UPDATE memberdef SET name = ? WHERE rowid = ?", (real, rowid))
    return True


## @brief Repair memberdefs doxygen mis-named '__attribute__' to the real name.
##
## A function with a leading `__attribute__((...))` on its own line above the
## signature is recorded by doxygen with memberdef name '__attribute__'
## (owning the real body span) — so lookups + AST edges misattribute it.
## '__attribute__' is never a valid function name. Runs after fix_doxygen_paths
## (paths repo-relative) and before the AST edge layers, so the corrected name
## + single row are in place before call/shared-key edges resolve. Returns
## rows repaired.
## @version 3
## @return Number of memberdef rows whose mis-recorded '__attribute__' name was repaired.
## @req REQ-DDB-INDEX-001
def repair_attribute_named_functions(db_path: Path, repo_root: Path) -> int:
    try:
        from tree_sitter import Language, Parser
    except ImportError:
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT m.rowid, m.bodystart, m.bodyend, m.file_id, p.name "
            "FROM memberdef m JOIN path p ON m.bodyfile_id = p.rowid "
            "WHERE m.name = '__attribute__' AND m.kind = 'function' "
            "AND m.bodystart > 0",
        ).fetchall()
        cache: dict = {}
        fixed = 0
        for rowid, bstart, bend, file_id, rel in rows:
            real = _real_function_name_at(repo_root, rel, bstart, cache, Parser, Language)
            if real and real != "__attribute__":
                _repair_one_attribute_row(conn, rowid, bstart, bend, file_id, real)
                fixed += 1
        conn.commit()
    finally:
        conn.close()
    if fixed:
        logger.info("Repaired %d __attribute__-mislabeled function name(s)", fixed)
    return fixed


## @brief Warn when source files were indexed but yielded no function bodies.
## @param db_path Database to inspect.
## @return Number of indexed source files that produced no body, 0 when fine.
## @version 3
## @req REQ-DDB-INDEX-001
def warn_if_no_function_bodies(db_path: Path) -> int:
    """A build that indexes source and extracts NOTHING from it is almost always
    a preprocessor problem, and it reports success either way.

    MEASURED on a real C library whose implementation sits behind
    `#if defined(<FEATURE>_C)` guards: 30 `.c` files present in `path`, **zero**
    functions with a body in any of them, and a normal summary printed. A
    consumer received a well-formed database describing a library with no
    implementation. Supplying `PREDEFINED` for the feature macros took the same
    build to 322 bodies.

    Deliberately a WARNING, not a failure, and deliberately not a fix: clew
    must never guess a target's feature macros — that is the target's
    declaration to make. But the ratio is never legitimately zero for a real
    C/C++ codebase, so silence here is the wrong default. This is the same class
    as every other "the layer is empty, and empty means four different things"
    problem: say which one it is.

    Headers alone are not enough to conclude anything — a header-only library or
    a docs-oriented Doxyfile (`FILE_PATTERNS = *.h`) legitimately has no bodies —
    so the check requires INDEXED IMPLEMENTATION FILES before it fires.

    @brief Warn when implementation files yielded no function bodies.
    @return Count of implementation files indexed with zero bodies.
    @version 3
    """
    impl = ("%.c", "%.cpp", "%.cc", "%.cxx")
    conn = sqlite3.connect(str(db_path))
    try:
        clause = " OR ".join("p.name LIKE ?" for _ in impl)
        files = conn.execute(
            f"SELECT COUNT(*) FROM path p WHERE {clause}",
            impl,
        ).fetchone()[0]
        if not files:
            return 0
        bodies = conn.execute(
            "SELECT COUNT(*) FROM memberdef m JOIN path p ON p.rowid = m.bodyfile_id "
            f"WHERE m.kind='function' AND ({clause})",
            impl,
        ).fetchone()[0]
    finally:
        conn.close()

    if bodies:
        return 0
    logger.warning(
        "%d implementation file(s) were indexed but NOT ONE yielded a function body. "
        "The usual cause is a preprocessor guard the build did not satisfy — if this "
        "repo wraps its code in feature macros, its Doxyfile needs PREDEFINED for "
        "them. Every AST and call-graph layer will read empty against this index",
        files,
    )
    return files


## @brief Express an absolute path relative to the repo root.
## @param path Absolute path as stored.
## @param repo_root Repository root.
## @return Relative name, or None when the path lies outside the repo.
## @version 2
## @dg_internal
def _under_root(path: Path, repo_root: Path) -> str | None:
    """@brief Make an absolute stored path repo-root-relative.

    @return Relative name, or None when it is outside the repo root.
    @version 2
    """
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return None


## @brief Rebuild a stripped path by re-attaching a STRIP_FROM_PATH prefix.
## @param name Stored (stripped) path name.
## @param strip_dirs Candidate prefixes to try.
## @param repo_root Repository root.
## @return Relative name, or None when no prefix reconstructs an existing file.
## @version 1
## @dg_internal
def _reattached(name: str, strip_dirs: list[Path], repo_root: Path) -> str | None:
    """@brief Re-attach each STRIP_FROM_PATH prefix until one names a real file.

    @return Relative name, or None.
    @version 1
    """
    for strip_dir in strip_dirs:
        candidate = strip_dir / name
        if candidate.exists():
            resolved = _under_root(candidate, repo_root)
            if resolved is not None:
                return resolved
    return None


## @brief Repo-root-relative form of a stripped path, or None.
## @param name Stored path name.
## @param strip_dirs Candidate STRIP_FROM_PATH prefixes to re-attach.
## @param repo_root Repository root.
## @return The relative name, or None when it cannot be reconstructed.
## @version 2
## @dg_internal
def _relative_name(name: str, strip_dirs: list[Path], repo_root: Path) -> str | None:
    """Handles the ABSOLUTE case first, because the obvious "is it already fine?"
    test cannot see it: `Path("/repo") / "/abs/p"` returns `/abs/p`, which exists,
    so an absolute name passes an existence check designed to skip correct rows.
    That is how absolute names survived this function — the guard was structurally
    blind to the one violation it exists to catch.

    @brief Reconstruct a repo-root-relative name.
    @return Relative name, or None if it is not under the repo root.
    @version 2
    """
    if name.startswith("/"):
        return _under_root(Path(name), repo_root)
    if (repo_root / name).exists():
        return name
    return _reattached(name, strip_dirs, repo_root)


## @brief Rewrite path table entries to be repo-root-relative.
## @param db_path Database to rewrite.
## @param doxyfile Doxyfile whose STRIP_FROM_PATH was used.
## @param repo_root Repository root.
## @return None.
## @version 3
## @req REQ-DDB-INDEX-001
def fix_doxygen_paths(db_path: Path, doxyfile: Path, repo_root: Path) -> None:
    """Enforce the contract that `path.name` is REPO-ROOT-RELATIVE.

    Doxygen's STRIP_FROM_PATH removes directory prefixes from stored paths, which
    makes them unusable for reading a file back, so this reconstructs the full
    repo-root-relative path from the known INPUT directories.

    IT NOW RUNS EVEN WITHOUT STRIP_FROM_PATH, and that is the fix. Previously it
    returned early when the Doxyfile declared none — reasonable-sounding, since
    with no stripping there is nothing to reconstruct, but it left ABSOLUTE names
    stored verbatim. `path.name` is published by `list_files` and `search` over
    MCP, so a shared database disclosed the build machine's directory layout.

    #97 fixed this for the SYNTHESIZED Doxyfile by forcing STRIP_FROM_PATH there,
    and this function's own docstring then claimed "only the repo-supplied-Doxyfile
    path produced relative names". **That was measurably false.** A repo shipping
    its own Doxyfile whose STRIP_FROM_PATH covers only part of its tree keeps
    absolute names for everything else — measured on a real C++ target: 145 of 474
    rows absolute, each carrying the builder's home directory, all of them under
    paths its STRIP_FROM_PATH did not mention.

    A repo still OWNS its STRIP_FROM_PATH — that declaration is not overridden.
    What is enforced is the post-condition, which is clew's own contract.

    @brief Fix doxygen paths so they resolve from the repo root.
    @return None.
    @version 3
    """
    strip_raw = parse_doxyfile_value(doxyfile, "STRIP_FROM_PATH")
    doxyfile_dir = doxyfile.parent
    strip_dirs = [(doxyfile_dir / d).resolve() for d in (strip_raw or "").split()]

    conn = sqlite3.connect(str(db_path))
    try:
        ## EVERY row, not just `type = 1`. The filter used to read files only, and
        ## directory rows (`type = 2`) kept absolute names for exactly the same
        ## reason — 32 of them on a real C++ target, each naming the builder's home
        ## directory. A privacy contract that holds for one row type and not another
        ## is not a contract.
        rows = conn.execute("SELECT rowid, name FROM path").fetchall()
        fixed, external = 0, 0
        for rowid, name in rows:
            resolved = _relative_name(name.rstrip("/"), strip_dirs, repo_root)
            if resolved is None:
                ## Outside the repo root entirely (a vendored include, a system
                ## header). Storing the absolute name is the disclosure, so keep
                ## only the final component and count it — loudly, since a large
                ## number here means the index scope reaches outside the repo.
                external += 1
                conn.execute(
                    "UPDATE path SET name = ? WHERE rowid = ?",
                    (Path(name.rstrip("/")).name, rowid),
                )
                continue
            if resolved != name:
                conn.execute("UPDATE path SET name = ? WHERE rowid = ?", (resolved, rowid))
                fixed += 1
        conn.commit()
    finally:
        conn.close()

    if fixed:
        logger.info("path: rewrote %d/%d entries to repo-root-relative", fixed, len(rows))
    if external:
        logger.warning(
            "path: %d entries resolved OUTSIDE %s and were reduced to their basename "
            "— an absolute path here would disclose this machine's layout",
            external,
            repo_root,
        )
