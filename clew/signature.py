# SPDX-License-Identifier: MIT
"""Build-version signature stamped into every built clew.db.

The pipeline owns the constant and the stamping (a `build_meta` row written
as the LAST stage, so a partial build never leaves a DB looking current).
Consumers own the freshness *check*: they compare `read_build_signature` against
the version they expect and treat a missing or older signature as stale — which
catches config and logic staleness that file mtimes cannot see.

THIS FILE IS THE ONLY HOME OF THE CONSTANT. It used to say a downstream consumer
kept its own copy in `core/docs_build.py` and that both had to be bumped
together; the 2026-07-23 pivot RETIRED that rule when this repo became
independent, and CLAUDE.md now states there is no dual-constant obligation and no
byte-alignment with any consumer. A consumer reconciles on its own timeline.

Bump it freely, and record WHY in the numbered comment below — a version whose
reason is unrecorded cannot tell anyone whether their index must be rebuilt,
which is the comment's whole job.

@brief clew.db build-version signature (constant + stamp + read).
@version 3
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .tiers import OPTIONS_META_PREFIX

## THE SCHEMA VERSION OF A BUILT INDEX. Bump it whenever a build produces different rows,
## columns or layers than the previous one did — a consumer detects a stale index by comparing
## this against the value stamped in `build_meta`, and that comparison is the only thing keeping
## an older index from being read as though it held layers it never had.
##
## It is deliberately OUTSIDE semver: the SQLite schema is not part of the covered surface, so a
## bump here is not a major version. `db_status` reports the two integers and `freshness` turns
## them into the schema staleness axis.
##
## A BUMP MAKES EVERY EXISTING INDEX STALE, and the pipeline's own cache honours that — the
## sidecar drops all entries when this changes, so a stale payload cannot answer a new question
## with silence.
CLEW_BUILD_VERSION = 1


## @brief Stamp the build version, scope, coverage and preprocessor config into build_meta.
## @param db_path Path to the built clew.db.
## @param version Version to stamp (defaults to CLEW_BUILD_VERSION).
## @param scope Optional {key: value} provenance for WHY this file set was indexed.
## @param coverage Optional {key: value} measurement of how much of it yielded symbols.
## @param preprocessor Optional {key: value} record of WHICH VARIANT was indexed.
## @param kconfig Optional {key: value} record of WHICH VARIANTS EXIST, and how the parse went.
## @param refresh Optional {key: value} record of WHAT THIS BUILD COST to run.
## @param options Optional {key: value} record of WHICH TIER chose each layered setting.
## @param diagnostics Optional {key: value} record of WHAT THE BUILD LOOKED FOR AND DID NOT FIND.
## @param data_model Optional {key: value} record of the generated DATA MODEL the repository declares.
## @param declaration Optional {key: value} record of the DOCUMENT an operator stated for this build.
## @version 13
## @req REQ-DDB-PIPE-005
## @req REQ-DDB-CONFIG-006
## @req REQ-DDB-CONFIG-007
def write_build_signature(
    db_path: Path | str,
    version: int = CLEW_BUILD_VERSION,
    scope: dict[str, str] | None = None,
    coverage: dict[str, str] | None = None,
    preprocessor: dict[str, str] | None = None,
    kconfig: dict[str, str] | None = None,
    refresh: dict[str, str] | None = None,
    options: dict[str, str] | None = None,
    diagnostics: dict[str, str] | None = None,
    data_model: dict[str, str] | None = None,
    declaration: dict[str, str] | None = None,
) -> None:
    """WHY THE FILE SET IS WHAT IT IS, recorded rather than only logged.

    `scope.DerivedScope` already carries the source (`declared` / `doxygen-guard` /
    `doxyfile`), a human-readable reason, and the roots and excludes — and its own docstring
    says it exists "so the BUILD LOG can always say which scope was used and why". The log is
    gone by the time anyone queries the index, so a consumer could see WHAT was indexed and
    never WHY.

    Measured on the entropic acceptance grid: the raw arm scored 3/3 on "checks the Doxyfile
    and reports that its INPUT does not list examples/" and the index arm 1/3 — the only
    clearly actionable gap in 56 marks. An agent could not ask why a file was or was not
    indexed, because nothing in the database answered it. `build_meta` held exactly one key.

    Written under a `scope.` prefix so the namespace stays legible as build_meta grows, and
    absent rather than empty when no scope was derived — a missing key means "not recorded",
    which is honest, while `scope.source=""` would read as a decision that was made and was
    blank.

    COVERAGE rides along for the same reason, and against the same defect: index SIZE
    was reported and index COVERAGE was not, so a build could announce thousands of
    functions for a target whose index held almost none of the library (gh#6 — 184 of
    221 implementation files yielded at most one symbol, and nothing said so). A
    coverage number that lives only in a build warning is gone by query time exactly
    as the scope decision was.

    Every section is namespaced and written by the same prefixing pass, so a further
    section is a one-line change rather than another copy of this loop. gh#17 was that
    one line, and it is the third leg of the same argument: `scope.*` says WHICH FILES
    were indexed, `coverage.*` says how much of them yielded anything, and
    `preprocessor.*` says WHICH VARIANT of them the index describes. A multi-variant
    codebase — anything with a config header — produces a different set of FUNCTIONS per
    configuration, so without that last section two indexes of one repo can disagree
    about whether a symbol exists at all and nothing in either explains it.

    `kconfig.*` is the FOURTH leg and the one that is not about this build at all.
    `scope.*` says which files were indexed, `coverage.*` how much of them yielded
    anything, `preprocessor.*` which variant of them this index describes — and
    `kconfig.*` says which variants the repository HAS, which is a fact about the
    repository rather than about the index. It carries `kconfig.error` for the same
    reason `preprocessor` records a macro count of zero: a Kconfig that was found and
    could not be parsed is a finding, and it is the finding a Zephyr application
    indexed outside its west workspace produces.

    `refresh.*` is the FIFTH leg and the only one about the BUILD rather than about the
    repository or the index's contents: what this run cost in wall milliseconds, how many
    files it reprocessed, and how many it took from cache. Same argument as the other
    four, one step further — a cost that lives only in a log line is gone by the time an
    agent has to decide whether correcting a stale index is worth it, and an agent that
    cannot measure the correction estimates it badly (gh#9: two acceptance marks demanding
    a measured number, missed in 9 of 9 cells at every model tier).

    It is also the section most exposed to the falsy-drop rule below, because a fully
    cached build legitimately reprocesses ZERO files and a small build legitimately takes
    under a millisecond. Callers pass strings; `"0"` survives where `0` would not.

    `options.*` is the SIXTH leg and the first that records a DECISION rather than a
    measurement (gh#319). The other five say what was indexed, how much of it yielded
    anything, which variant it describes, which variants exist and what the run cost;
    this one says which precedence TIER supplied a layered setting — an operator's
    flag, the target's declaration, or our own provisional guesses. Without it a
    liveness split computed from a repo's declared dispatch vocabulary is
    indistinguishable from one computed from `%handler%`, and the whole point of
    resolving in tiers is lost the moment the winner is not written down.

    Its values come from `tiers.options_meta`, which accepts only `LayeredResolution` and
    `DocumentResolution` objects — so this section cannot be populated from values whose
    provenance was discarded on the way here. A `DocumentResolution` also carries the
    stated manifest itself, as canonical JSON, because a tier-1 statement is REPLAYED onto
    a later build (gh#364) and a policy that is applied but never recorded is discarded by
    the next refresh, which then reports success over a different one.

    `diagnostics.*` is the SEVENTH leg and the only one that records what is NOT in the
    index (gh#320). The other six describe rows that exist; this one names the accessor
    families and event alias tags the build searched for, did not claim, and therefore
    wrote no rows for. It carries its counts as STRINGS for the reason the falsy-drop rule
    above demands and `refresh` already illustrates — the zero is the measurement here, so
    dropping it would leave "searched and found nothing" indistinguishable from "never
    looked", which is the exact ambiguity the section exists to remove.

    `data_model.*` is the EIGHTH leg (gh#351) and, like `kconfig.*`, it describes the
    REPOSITORY rather than the index: which generated data model the repository declares, how
    many keys and classes it carries, and how many of those keys the code was observed to
    touch. Its refusals are the actionable half — `data_model.manifests_unlisted` says
    manifest documents were found and declined for want of a key list to vouch for them,
    which is the difference between a repository with no data model and one whose model
    nothing selects. Counts are STRINGS for the falsy-drop reason above.

    `declaration.*` is the NINTH leg, and it is the only one that records what an OPERATOR
    stated rather than what the repository contains. `options.*` records which TIER won per
    option, which is not the same claim: a document stated with `--declare` can be applied,
    recorded per-option, and then partly LOST on a later build, because only tier-1 statements
    replay and a section added to the document after that build never reaches the index at all.
    Measured 2026-08-14 on the mbedtls acceptance target, and it invalidated a graded run: the
    committed declaration declared `locks`, `vendored` and `preprocessor`; the graded index
    held `options.locks.tier=explicit` (replayed from an older build) and
    `options.predefined.tier=heuristic` with no `vendored` row anywhere. The measurement looked
    healthy from every angle a reader had, because nothing recorded WHICH DOCUMENT was stated.

    CONTENT-ADDRESSED, and no per-section knowledge. `stated_sha256` is over the document's
    bytes and `stated_sections` names its top-level keys, so a checker compares the file it
    holds against the build with no map from section name to the evidence that section leaves.
    That absence of a map is the point: `preprocessor:` lands as `options.predefined.*` and
    `vendored:` leaves no `options.*` row at all, so any such map is a second vocabulary free
    to drift as sections are added — and the section it forgot would be the silent one.

    NO PATH IS STORED. The stated document lives in the CONSUMER'S tree, not the target's, so a
    path here would publish the builder's machine layout over MCP — the disclosure that forced
    the build-version-9 bump, one key further out. A sha and a section list identify the
    document exactly without saying where on disk it sat.

    @brief Stamp the build version and optional scope, coverage, preprocessor, kconfig, refresh, options, diagnostics, data_model and declaration sections.
    @version 13
    """
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS build_meta (key TEXT PRIMARY KEY, value TEXT)")
        rows = [("build_version", str(version))]
        ## Falsy values are DROPPED, so an absent key honestly reads as "not recorded"
        ## rather than as a decision that was made and was blank. Coverage therefore
        ## passes its numbers as STRINGS — a measured zero must be recorded, and `"0"`
        ## is truthy where `0` is not.
        for prefix, section in (
            ("scope", scope),
            ("coverage", coverage),
            ("preprocessor", preprocessor),
            ("kconfig", kconfig),
            ("data_model", data_model),
            ("refresh", refresh),
            ## Imported rather than spelled again, because `cli` READS this section
            ## back to replay a recorded statement and a drifted prefix would replay
            ## nothing while the stamp still looked healthy. The four literals above
            ## predate the constant and are written once here and once in `cli`;
            ## churning them is unrelated work.
            (OPTIONS_META_PREFIX, options),
            ## A LITERAL, deliberately, though `diagnostics.META_PREFIX` exists. Importing
            ## it here would pull `shared_key_edges` and `event_edges` — and tree-sitter
            ## behind them — into every import of this near-leaf module. The drift that
            ## constant guards against is instead pinned by a ROUND-TRIP test, which
            ## catches a divergence in either spelling rather than only in this one.
            ("diagnostics", diagnostics),
            ## The NINTH leg (P0.1). Prefixed here rather than by its producer for the same
            ## reason every other section is: one prefixing pass means a further section is a
            ## one-line change, and a reader learns the whole namespace from this tuple.
            ("declaration", declaration),
        ):
            rows += [(f"{prefix}.{k}", v) for k, v in sorted((section or {}).items()) if v]
        conn.executemany(
            "INSERT INTO build_meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


## @brief Read the build version stamped into a DB, or None if absent/unreadable.
## @param db_path Path to a clew.db.
## @return Stamped version int, or None when missing or unreadable.
## @version 2
## @req REQ-DDB-PIPE-005
def read_build_signature(db_path: Path | str) -> int | None:
    row = None
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT value FROM build_meta WHERE key = 'build_version'"
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        row = None
    if not row:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return None


## The table every built index has, whatever else is missing. Layer tables are
## conditional — a repo with no locks has no `lock_acquisitions` — but doxygen
## always produces `memberdef`, so it is the one honest "is this an index at all"
## probe.
_INDEX_SENTINEL_TABLE = "memberdef"


## @brief Why a path is not a usable index, or "" when it is one.
## @param db_path Path that is supposed to hold a built index.
## @return A human-readable reason, or "" when the database is usable.
## @version 2
## @req REQ-DDB-PIPE-005
def index_unusable_reason(db_path: Path | str) -> str:
    """ONE rule, in one place, because there were two behaviours and the wrong one
    shipped in the more visible surface.

    `sqlite3.connect` on a nonexistent path CREATES an empty database. Nothing
    raises; every `table_exists` guard downstream correctly answers False; and the
    HTML explorer emitted a structurally valid document describing zero functions.
    That is worse than a traceback: a traceback is a question, and a plausible
    empty report is a wrong answer. The proposer already refused a zero-byte
    `clew.db` for exactly this reason — this makes that the shared rule rather than
    one module's good habit.

    Deliberately NOT used by `query/_common.connect`. The query layer's contract is
    the opposite one and was settled on purpose: it DEGRADES on a partial database
    so a consumer gets empty results rather than an exception, since a stale index
    missing a later layer is a normal thing to query. This helper is for surfaces
    that PRODUCE something — an emitted document, a served page, a build — where
    proceeding means publishing a falsehood.

    Returns a reason rather than raising or returning a bool: the caller decides
    the exit code and gets a message it can print next to a rebuild command,
    without either restating the checks or losing which one failed.

    @brief Judge whether a path holds a usable index, and say why not.
    @return Reason string, empty when usable.
    @version 2
    """
    path = Path(db_path)
    return _filesystem_problem(path) or _sqlite_problem(path)


## @brief Why a path could not be a database at all, before opening it.
## @param path Candidate index path.
## @return Reason string, empty when the path is at least a non-empty file.
## @version 1
## @dg_internal
def _filesystem_problem(path: Path) -> str:
    """Checked in this order because each step is the precondition for the next:
    `stat()` raises on a missing path, so the existence test cannot be folded in
    alongside the size test.

    Written as one assignment rather than early returns to stay inside the
    max-3-returns standard — which caught the first draft of this function at six.

    @brief Judge a candidate path without opening it as a database.
    @return Reason string, empty when the path could be a database.
    @version 1
    """
    problem = ""
    if not path.exists():
        problem = f"no database at {path}"
    elif not path.is_file():
        problem = f"{path} is not a file"
    elif path.stat().st_size == 0:
        problem = f"{path} is zero bytes — an earlier build almost certainly failed partway"
    return problem


## @brief Why an existing file is not a readable index, once opened.
## @param path A path already known to be a non-empty file.
## @return Reason string, empty when the file is a database holding the sentinel table.
## @version 1
## @dg_internal
def _sqlite_problem(path: Path) -> str:
    """Opened READ-ONLY via a `file:` URI on purpose: the whole point of this
    helper is that the ordinary `sqlite3.connect(path)` CREATES a database, so
    probing with the same call that causes the bug would be self-defeating.

    @brief Probe an existing file for the index sentinel table.
    @return Reason string, empty when it is a usable index.
    @version 1
    """
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return f"{path} cannot be opened as a database ({exc})"
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (_INDEX_SENTINEL_TABLE,),
        ).fetchone()
    except sqlite3.Error as exc:
        return f"{path} is not readable as a database ({exc})"
    finally:
        conn.close()
    return "" if row else f"{path} has no {_INDEX_SENTINEL_TABLE} table — it is not an index"
