# SPDX-License-Identifier: MIT
"""Index COVERAGE — how much of what was indexed actually yielded anything.

Index SIZE is not index coverage, and until this module existed only size was
reported. gh#6: a build announced "2,555 functions and 28,151 call edges" for a
target whose index contained almost none of the library — 184 of 221
implementation files yielded at most one symbol, 162 of them over 100 lines,
including a 9,969-line file with zero. Nothing in the build output, `status`, or
any query reply said so. A 198-cell acceptance run was then executed against
that index and voided, at a cost of roughly 318M tokens to discover after the
fact. This check existing would have refused that run before it started.

WHAT COUNTS AS BARREN, and why it is not an extension list. The no-hardcoding
mandate forbids baking in one language's conventions, and `.c`/`.cpp` — the
issue's own framing — is wrong for a repo this tool also indexes in Python. The
metric is instead the issue's own measured one, which happens to be
language-agnostic: **a file that produced at most one `memberdef` row**. That
separates the cases without naming any language, because a header DECLARES (its
declarations are memberdef rows) while a file whose body sits inside an
unsatisfied preprocessor guard produces nothing at all. Measured: mbedtls's
`library/threading.c` yields exactly one symbol, `_POSIX_C_SOURCE`.

Two attributions are unioned, and the union is load-bearing. doxygen records a
C++ method declared in a header and defined in a `.cpp` with `file_id` = the
HEADER and `bodyfile_id` = the `.cpp` (the decl/def duality). Counting `file_id`
alone therefore reports a fully-indexed translation unit as barren: measured on
entropic, `src/mcp/server_manager.cpp` shows 1 row by `file_id` and 33 bodies by
`bodyfile_id`. Counting bodies alone is wrong in the other direction — a real
header legitimately has none, so 85% of mbedtls's headers would read barren.

Documentation files are excluded, by EXTENSION and by prose yield. A markdown file
is not barren, it is not code. Without this, mbedtls's 27 substantive `.md` files
read 100% barren and inflate the headline. Extension is the primary test because
`supplementary_docs` membership answers the narrower question "was this file
ingested", and an index whose INPUT is wider than the ingestion file set otherwise
counts un-ingested markdown as barren code.

Calibration, on the two targets the issue names plus this repo's own Python
self-index (all three public — see CLAUDE.md MEASUREMENT PROVENANCE):

| target   | substantive files | barren | ratio |
|----------|-------------------|--------|-------|
| mbedtls  | 374               | 190    | 50.8% |
| entropic | 177               |   7    |  4.0% |
| docs-db  | 116               |   1    |  0.9% |

`WARN_RATIO` is 0.25 — an order of magnitude above the worst benign case and
half the defect. entropic's residue is genuinely inapplicable code (Windows and
Darwin platform files inside a vendored fuzzer) and docs-db's single offender is
a re-export `__init__.py`; a check that fired on either would be worse than no
check, which this project has shipped before and CLAUDE.md records.

DELIBERATELY NOT A GATE. A repo can legitimately be in this state, and refusing
to index it would make the tool useless exactly when a consumer most needs to
see why the index is thin. Loud and queryable, never fatal.

gh#11 ADDED A SECOND MEASUREMENT beside every number above. Recovering the
function definitions doxygen never emitted makes the barren ratio fall — that is
the acceptance criterion for that change — and it would also silence the warning
above, whose advice (declare `PREDEFINED`) is still the better fix. So every count
here has an `undocumented` twin measured over doxygen-sourced rows only. The
barren ratio says whether the index can be REASONED ABOUT; the undocumented ratio
says whether it can be READ.

@brief Measure and report how much of the indexed file set yielded symbols.
@version 3
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .vocabulary import EXTERNAL_ROOT_COLUMN, SYMBOL_SOURCE_COLUMN, SYMBOL_SOURCE_DOXYGEN

logger = logging.getLogger(__name__)

## A file below this many lines yielding nothing proves nothing — a stub header, an
## `__init__.py` of re-exports, a licence banner. 100 is the issue's own framing, and
## it is what takes entropic's residue from 32 files to 4.
MIN_SUBSTANTIVE_LINES = 100

## Documentation extensions doxygen accepts as input. A file with one of these is
## excluded from the coverage denominator whether or not prose ingestion reached it:
## it cannot yield a `memberdef` row, so counting it measures the file type and not
## the index.
_DOC_SUFFIXES = (".md", ".markdown", ".dox", ".txt", ".rst")

## Below this many substantive files a ratio is noise, not a measurement: two files,
## one barren, is 50% and means nothing. Every real target measures 116+.
MIN_SUBSTANTIVE_FILES = 20

## Measured benign 0.9%-4.0%, measured defect 50.8%. See the table above.
WARN_RATIO = 0.25

## The issue reported five. Enough to name the pattern, few enough not to be a wall
## of paths that trains the reader to skip the warning.
OFFENDER_LIMIT = 5


## @brief One indexed file and what it yielded.
## @version 3
@dataclass(frozen=True)
class FileYield:
    """A single indexed source file: its repo-relative path, its line count, and
    how many memberdef rows were attributed to it under the unioned
    file_id/bodyfile_id attribution — in total, and restricted to the rows doxygen
    itself documented.

    `documented_symbols` defaults to 0 rather than to `symbols` so a hand-built
    FileYield cannot silently assert full documentation it was never given.

    @brief An indexed file's line count and symbol yield.
    @version 3
    """

    path: str
    lines: int
    symbols: int
    documented_symbols: int = 0
    ## Which nested foreign git tree owns this file (gh#335), or '' for first party.
    ## Defaults to first party so a hand-built FileYield cannot silently disown
    ## itself out of the denominator — the direction that would make a coverage
    ## ratio look healthy by measuring less.
    external_root: str = ""
    ## Whether this `path` row names a file that actually exists under the repo root.
    ## False for an unresolved `#include` doxygen recorded by bare filename. Defaults
    ## True for the same reason `external_root` defaults to first party: a hand-built
    ## FileYield must not disown itself out of the denominator.
    resolved: bool = True

    ## @brief Whether this file is large enough for its yield to mean anything.
    ## @return True when the file has at least MIN_SUBSTANTIVE_LINES lines.
    ## @version 1
    ## @req REQ-DDB-INDEX-003
    @property
    def substantive(self) -> bool:
        """@brief Is the file big enough to judge?

        @return True when at or above the line floor.
        @version 1
        """
        return self.lines >= MIN_SUBSTANTIVE_LINES

    ## @brief Whether this file yielded essentially nothing.
    ## @return True when at most one memberdef row was attributed to it.
    ## @version 1
    ## @req REQ-DDB-INDEX-003
    @property
    def barren(self) -> bool:
        """At most ONE row, not zero: mbedtls's `threading.c` yields exactly one
        symbol (`_POSIX_C_SOURCE`, a define) with its entire body guarded out, so
        a strict-zero test misses the canonical case.

        @brief Did this file yield at most one symbol?
        @return True when symbols <= 1.
        @version 1
        """
        return self.symbols <= 1

    ## @brief Whether this file yielded essentially no DOCUMENTED symbol.
    ## @return True when at most one doxygen-sourced memberdef row was attributed to it.
    ## @version 1
    ## @req REQ-DDB-INDEX-004
    @property
    def undocumented(self) -> bool:
        """The same test over doxygen-sourced rows ONLY (gh#11). Once
        `ast_symbols.recover_ast_symbols` inserts parser-recovered rows, `barren`
        correctly stops firing — the index really does hold those symbols now — and
        this property is what keeps the DOCUMENTATION gap visible. A file that is
        `undocumented` but not `barren` is one whose graph was recovered and whose
        prose was not, which is precisely the case where declaring `PREDEFINED`
        (gh#17) is still the better answer.

        @brief Did this file yield at most one documented symbol?
        @return True when documented_symbols <= 1.
        @version 1
        """
        return self.documented_symbols <= 1


## @brief Coverage measurement over one built index.
## @version 3
@dataclass(frozen=True)
class IndexCoverage:
    """The numbers gh#6 asks for: how many files were indexed, how many were big
    enough to judge, how many of those yielded nothing, and which were largest —
    plus gh#11's twin, the same over doxygen-sourced rows only.

    FIRST PARTY BY DEFAULT (gh#335). Once a nested git tree is indexed rather than
    excluded, an unqualified coverage ratio averages this repo with somebody else's
    and the resulting number describes neither. A vendored dependency's barren
    headers are not a defect in the repo that vendored it, and the advice the warning
    gives — declare PREDEFINED — is not advice its owner can act on.

    @brief First-party indexed-vs-yielding counts, plus the external population.
    @version 3
    """

    indexed_files: int
    substantive_files: int
    barren_files: int
    offenders: tuple[FileYield, ...]
    undocumented_files: int = 0
    undocumented_offenders: tuple[FileYield, ...] = ()
    ## gh#335. EVERY FIELD ABOVE IS FIRST PARTY ONLY. These two say how much was left
    ## out, so a reader can tell a repo with no submodule from one whose vendored
    ## dependency was silently dropped from the denominator — the second is a
    ## measurement of less, and reporting it as the same number would be the
    ## "filtered answer that looks like an empty answer" failure in aggregate form.
    external_files: int = 0
    external_roots: tuple[str, ...] = ()
    ## `path` rows that resolve to no file in this repository — doxygen's record of
    ## an `#include` it could not resolve, spelled as a bare filename. Neither first
    ## party nor attributable to a named tree, so counted apart from both rather than
    ## defaulted into either.
    unresolved_files: int = 0

    ## @brief Barren share of the substantive file set.
    ## @return Ratio in 0.0-1.0; 0.0 when nothing was substantive.
    ## @version 1
    ## @req REQ-DDB-INDEX-003
    @property
    def barren_ratio(self) -> float:
        """@brief Fraction of judgeable files that yielded nothing.

        @return barren/substantive, or 0.0 when the denominator is zero.
        @version 1
        """
        if not self.substantive_files:
            return 0.0
        return self.barren_files / self.substantive_files

    ## @brief Undocumented share of the substantive file set.
    ## @return Ratio in 0.0-1.0; 0.0 when nothing was substantive.
    ## @version 1
    ## @req REQ-DDB-INDEX-004
    @property
    def undocumented_ratio(self) -> float:
        """Always >= `barren_ratio`, because a documented symbol is also a symbol.
        The two are equal on a build with no recovered rows, which is why adding
        this measurement changed no existing number on a healthy target.

        @brief Fraction of judgeable files with no documented symbol.
        @return undocumented/substantive, or 0.0 when the denominator is zero.
        @version 1
        """
        if not self.substantive_files:
            return 0.0
        return self.undocumented_files / self.substantive_files

    ## @brief Whether the DOCUMENTATION gap is worth saying out loud on its own.
    ## @return True when the sample is big enough, the doc ratio clears WARN_RATIO, and recovery has closed part of it.
    ## @version 1
    ## @req REQ-DDB-INDEX-004
    @property
    def recovered_but_undocumented(self) -> bool:
        """The condition under which gh#11's recovery has hidden gh#6's signal: the
        graph is now populated (`barren_ratio` below the threshold, so `alarming` is
        False) while the prose is not. Requires a STRICT gap between the two ratios
        — without it this fires on every alarming build as a duplicate of the main
        warning, which is how a second warning trains a reader to skip the first.

        @brief Does the documentation gap need its own warning?
        @return True when recovery closed the graph gap but not the prose gap.
        @version 1
        """
        return (
            self.substantive_files >= MIN_SUBSTANTIVE_FILES
            and self.undocumented_ratio >= WARN_RATIO
            and self.undocumented_files > self.barren_files
        )

    ## @brief Whether the barren share is high enough to be worth saying out loud.
    ## @return True when the sample is big enough AND the ratio clears WARN_RATIO.
    ## @version 1
    ## @req REQ-DDB-INDEX-003
    @property
    def alarming(self) -> bool:
        """Both terms are required. The ratio alone fires on a two-file toy index;
        the sample size alone says nothing about coverage.

        @brief Does this measurement warrant a warning?
        @return True when substantive_files >= floor and ratio >= WARN_RATIO.
        @version 1
        """
        return self.substantive_files >= MIN_SUBSTANTIVE_FILES and self.barren_ratio >= WARN_RATIO

    ## @brief Flatten to string values for build_meta persistence.
    ## @return Mapping of unprefixed coverage keys to string values.
    ## @version 3
    ## @req REQ-DDB-INDEX-003
    def as_meta(self) -> dict[str, str]:
        """Persisted because a coverage number that lives only in a warning has
        exactly the defect CLAUDE.md records for scope provenance: the pipeline
        computed it into the build LOG, which is gone by the time anyone queries.

        Values are STRINGS because `write_build_signature` drops falsy values, and
        a measured zero must be recorded — `"0"` is truthy, `0` is not.

        @brief Coverage facts as build_meta values.
        @return Unprefixed key → string value.
        @version 3
        """
        return {
            "indexed_files": str(self.indexed_files),
            "substantive_files": str(self.substantive_files),
            "barren_files": str(self.barren_files),
            "barren_ratio": f"{self.barren_ratio:.3f}",
            "largest_barren": ", ".join(f"{f.path}:{f.lines}" for f in self.offenders),
            ## gh#11. Persisted BESIDE the overall numbers rather than instead of them,
            ## because they answer different questions and a consumer needs both: the
            ## barren ratio says whether the index can be reasoned about, the
            ## undocumented ratio says whether it can be read.
            "undocumented_files": str(self.undocumented_files),
            "undocumented_ratio": f"{self.undocumented_ratio:.3f}",
            "largest_undocumented": ", ".join(
                f"{f.path}:{f.lines}" for f in self.undocumented_offenders
            ),
            ## gh#335. Persisted even when ZERO, because "this repo vendors nothing"
            ## and "this index predates the tag" are different facts and a consumer
            ## reading a healthy first-party ratio needs to tell them apart. `"0"` is
            ## truthy where `0` is not, which is why every value here is a string.
            "external_files": str(self.external_files),
            "external_roots": ", ".join(self.external_roots),
            "unresolved_files": str(self.unresolved_files),
        }


## @brief Count lines in a file without holding it in memory.
## @param path Absolute path to read.
## @return Line count, or -1 when the file cannot be read.
## @version 1
## @dg_internal
def _line_count(path: Path) -> int:
    """Returns -1 rather than 0 for an unreadable file so it is excluded from the
    substantive set instead of counted as a tiny file — a file we cannot measure
    must not become evidence either way.

    @brief Count newlines in a file.
    @return Line count, or -1 if unreadable.
    @version 1
    """
    try:
        with path.open("rb") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return -1


## @brief Symbols attributed to each indexed file, unioning decl and body attribution.
## @param conn Open connection to the built index.
## @param documented_only Restrict the count to doxygen-sourced rows.
## @return Mapping of path rowid → number of memberdef rows attributed.
## @version 3
## @dg_internal
def _symbols_by_file(conn: sqlite3.Connection, *, documented_only: bool = False) -> dict[int, int]:
    """The UNION is the decl/def duality, and it is load-bearing — see the module
    docstring. A memberdef is attributed to its declaring file (`file_id`) AND to
    the file holding its body (`bodyfile_id`); a C++ method has those be two
    different files, so either alone undercounts one of them. `UNION` (not
    `UNION ALL`) over `(rowid, file)` pairs keeps a row that declares and defines
    in the same file from counting twice.

    `documented_only` restricts the count to doxygen-sourced rows (gh#11), which is
    what separates "the index holds no symbol for this file" from "the index holds
    no DOCUMENTATION for this file". Tolerates the provenance column being absent —
    an index built before build version 19 has no `dg_source`, and there every row
    is doxygen's by construction, so the unfiltered count IS the documented count.

    @brief Per-file symbol yield under unioned attribution.
    @return path rowid → memberdef row count.
    @version 3
    """
    predicate = "IS NOT NULL"
    if documented_only and _has_provenance(conn):
        predicate = f"IS NOT NULL AND {SYMBOL_SOURCE_COLUMN} = '{SYMBOL_SOURCE_DOXYGEN}'"
    rows = conn.execute(
        "SELECT fid, COUNT(*) FROM ("
        f"  SELECT rowid AS mid, file_id AS fid FROM memberdef WHERE file_id {predicate}"
        "  UNION"
        f"  SELECT rowid AS mid, bodyfile_id AS fid FROM memberdef WHERE bodyfile_id {predicate}"
        ") GROUP BY fid"
    ).fetchall()
    return {fid: count for fid, count in rows}


## @brief Whether this index carries the memberdef provenance column.
## @param conn Open connection to the built index.
## @return True when `memberdef` has the provenance column.
## @version 1
## @dg_internal
def _has_provenance(conn: sqlite3.Connection) -> bool:
    """@brief Report whether `memberdef` carries the provenance column.

    @return True when the column is present.
    @version 1
    """
    return any(
        row[1] == SYMBOL_SOURCE_COLUMN for row in conn.execute("PRAGMA table_info(memberdef)")
    )


## @brief Repo-relative paths that contributed prose rather than symbols.
## @param conn Open connection to the built index.
## @return Set of file paths present in supplementary_docs.
## @version 1
## @dg_internal
def _prose_files(conn: sqlite3.Connection) -> set[str]:
    """A markdown file is not barren; it is not code. Tolerates the table being
    absent so the measurement still works on an index built before prose
    ingestion, or mid-pipeline.

    @brief Files that yielded prose.
    @return Set of repo-relative paths.
    @version 1
    """
    try:
        return {r[0] for r in conn.execute("SELECT DISTINCT file_path FROM supplementary_docs")}
    except sqlite3.Error:
        return set()


## @brief Per-file yields for every indexed source file.
## @param conn Open connection to the built index.
## @param repo_root Working tree the indexed paths are relative to.
## @return Tuple of FileYield, one per indexed non-prose source file.
## @version 4
## @dg_internal
def _file_yields(conn: sqlite3.Connection, repo_root: Path) -> tuple[FileYield, ...]:
    """The external tag is SELECTED, not joined from a second source. gh#335 stamps
    it onto `path`, which is the row this query already reads, so there is no way for
    the coverage view of "which files are foreign" to drift from the index's.

    Tolerates the column being absent: an index built before gh#335 has no tag, and
    there every file is first party BY CONSTRUCTION, because that build excluded
    nested git trees outright rather than admitting them untagged.

    @brief Join indexed paths against their symbol yield, line count and owner.
    @return One FileYield per indexed source file that is not documentation.
    @version 4
    """
    symbols = _symbols_by_file(conn)
    documented = _symbols_by_file(conn, documented_only=True)
    prose = _prose_files(conn)
    column = EXTERNAL_ROOT_COLUMN if _has_external_tag(conn) else "''"
    files = conn.execute(f"SELECT rowid, name, {column} FROM path WHERE type=1").fetchall()
    ## RESOLVED IS MEASURED HERE, off disk, rather than read from the stamped column.
    ## This function is also the pipeline's own measurement — it runs before the
    ## signature is written and the query layer reads the STAMP — so taking it from
    ## the column would make the measurement depend on its own output.
    return tuple(
        FileYield(
            path=name,
            lines=_line_count(repo_root / name),
            symbols=symbols.get(fid, 0),
            documented_symbols=documented.get(fid, 0),
            external_root=owner or "",
            resolved=(repo_root / name).is_file(),
        )
        for fid, name, owner in files
        if name not in prose and not _is_documentation(name)
    )


## @brief Whether this index carries the per-file external-provenance column.
## @param conn Open connection to the built index.
## @return True when `path` has the external-root column.
## @version 1
## @dg_internal
def _has_external_tag(conn: sqlite3.Connection) -> bool:
    """@brief Report whether `path` carries the external-root column.

    @return True when the column is present.
    @version 1
    """
    return any(row[1] == EXTERNAL_ROOT_COLUMN for row in conn.execute("PRAGMA table_info(path)"))


## @brief Whether an indexed path is documentation rather than code.
## @param name Repo-relative indexed path.
## @return True when the file's extension is a documentation extension.
## @version 1
## @dg_internal
def _is_documentation(name: str) -> bool:
    """BY EXTENSION, not by ingestion. `supplementary_docs` membership answers "was
    this file ingested as prose", which is a narrower question than "is this file
    code" — ingestion has its own configured file set, so an index whose INPUT is
    wider puts un-ingested markdown into the barren denominator and inflates a ratio
    that is supposed to say whether the CODE can be reasoned about.

    The suffixes are doxygen's own documentation extensions, not any repo's
    convention.

    @brief Test whether a path is a documentation file.
    @return True for a documentation extension.
    @version 1
    """
    return name.rsplit("/", 1)[-1].lower().endswith(_DOC_SUFFIXES)


## @brief Measure how much of the indexed file set actually yielded symbols.
## @param db_path Built index to measure.
## @param repo_root Working tree the indexed paths are relative to.
## @return IndexCoverage; an all-zero measurement when the index cannot be read.
## @version 3
## @req REQ-DDB-INDEX-003
def measure_index_coverage(db_path: Path, repo_root: Path) -> IndexCoverage:
    """FAILS SOFT to an all-zero measurement. This describes a build that has
    already succeeded; a measurement that raises must not destroy the index it is
    describing. An all-zero coverage is also what `alarming` correctly reads as
    "not enough sample to judge", so a failure here cannot manufacture an alarm.

    EXTERNAL FILES ARE PARTITIONED OUT BEFORE ANYTHING IS COUNTED (gh#335), which is
    also the control that says the tagging works: admitting a submodule must raise
    `external_files` and leave every first-party figure IDENTICAL. If a first-party
    number moves when a nested tree is admitted, the tag is wrong — that is a
    stronger check than any assertion about the matcher, because it holds whatever
    the matcher does.

    @brief Measure index coverage over one built database.
    @return The coverage measurement, first party unless a field says otherwise.
    @version 3
    """
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return IndexCoverage(0, 0, 0, ())
    try:
        yields = _file_yields(conn, Path(repo_root))
    except sqlite3.Error:
        yields = ()
    finally:
        conn.close()

    resolved = [f for f in yields if f.resolved]
    external = [f for f in resolved if f.external_root]
    first_party = [f for f in resolved if not f.external_root]
    substantive = [f for f in first_party if f.substantive]
    barren = [f for f in substantive if f.barren]
    undocumented = [f for f in substantive if f.undocumented]
    return IndexCoverage(
        indexed_files=len(first_party),
        substantive_files=len(substantive),
        barren_files=len(barren),
        offenders=tuple(sorted(barren, key=lambda f: -f.lines)[:OFFENDER_LIMIT]),
        undocumented_files=len(undocumented),
        undocumented_offenders=tuple(sorted(undocumented, key=lambda f: -f.lines)[:OFFENDER_LIMIT]),
        external_files=len(external),
        external_roots=tuple(sorted({f.external_root for f in external})),
        unresolved_files=len(yields) - len(resolved),
    )


## @brief Warn when the graph was recovered but the documentation was not.
## @param coverage Measurement to report.
## @version 1
## @dg_internal
def _log_documentation_gap(coverage: IndexCoverage) -> None:
    """gh#11's own honesty check. Recovering parser-visible symbols makes
    `barren_ratio` fall — which is the point, and is the acceptance criterion for
    that change — but it would ALSO silence gh#6's warning about the preprocessor,
    and the advice in that warning is still the better fix. So the two measurements
    are reported separately, and this one fires exactly when recovery has closed the
    graph gap and left the prose gap open.

    Ordered BEFORE the main coverage line on purpose: when both fire, the reader
    should see the specific claim before the general one.

    @brief Emit the documentation-gap warning when it is distinct from the coverage one.
    @version 1
    """
    if not coverage.recovered_but_undocumented:
        return
    logger.warning(
        "INDEX IS PARSED BUT NOT DOCUMENTED: %d of %d substantive file(s) — %.1f%% — yielded at "
        "most one DOCUMENTED symbol, against %.1f%% yielding no symbol at all. The difference is "
        "the functions recovered from the source text by the parser: they are in the call graph, "
        "and they carry NO brief, NO documented parameters and NO @req tags, because a "
        "preprocessor that skipped the code skipped its doc comment too. If this repo wraps its "
        "code in feature macros, its Doxyfile needs PREDEFINED for them — that recovers the "
        "documentation, which this cannot. Largest undocumented files: %s",
        coverage.undocumented_files,
        coverage.substantive_files,
        100.0 * coverage.undocumented_ratio,
        100.0 * coverage.barren_ratio,
        ", ".join(
            f"{f.path} ({f.lines} lines, {f.documented_symbols} documented)"
            for f in coverage.undocumented_offenders
        ),
    )


## @brief Log the coverage measurement, loudly when the barren share is high.
## @param coverage Measurement to report.
## @version 2
## @dg_internal
def _log_coverage(coverage: IndexCoverage) -> None:
    """Proportionate by design. The headline is the RATIO, because a raw count is
    unreadable without its denominator — "190 files yielded nothing" is alarming
    or unremarkable depending on whether the index holds 374 files or 40,000. The
    offenders are named with their line counts because that is what makes the
    warning actionable: a 9,969-line file with zero symbols is a preprocessor
    problem you can go and look at.

    @brief Emit the coverage line at INFO, or a warning when alarming.
    @version 2
    """
    if not coverage.substantive_files:
        return
    _log_documentation_gap(coverage)
    if not coverage.alarming:
        logger.info(
            "Index coverage: %d of %d substantive file(s) yielded no symbols (%.1f%%)",
            coverage.barren_files,
            coverage.substantive_files,
            100.0 * coverage.barren_ratio,
        )
        return
    logger.warning(
        "INDEX COVERAGE IS LOW: %d of %d substantive file(s) — %.1f%% — yielded at most one "
        "symbol. The index reports its SIZE, and that size describes only the files that "
        "were parsed successfully. The usual cause is a preprocessor guard the build did "
        "not satisfy: if this repo wraps its code in feature macros, its Doxyfile needs "
        "PREDEFINED for them. Largest files that yielded nothing: %s",
        coverage.barren_files,
        coverage.substantive_files,
        100.0 * coverage.barren_ratio,
        ", ".join(f"{f.path} ({f.lines} lines, {f.symbols} symbol(s))" for f in coverage.offenders),
    )


## @brief Measure index coverage, report it, and return it for persistence.
## @param db_path Built index to measure.
## @param repo_root Working tree the indexed paths are relative to.
## @return The IndexCoverage measurement.
## @version 2
## @req REQ-DDB-INDEX-003
def report_index_coverage(db_path: Path, repo_root: Path) -> IndexCoverage:
    """The single pipeline entry point, composing the TOTAL-absence term with the
    PARTIAL-absence one rather than competing with it.

    `doxygen.warn_if_no_function_bodies` is the all-or-nothing case: implementation
    files indexed and NOT ONE body anywhere. It keeps its own extension-based notion
    of an implementation file because that is what makes a header-only library safe,
    and it owns the most actionable advice we have. It is called FIRST and its
    warning suppresses this one, so a build that extracted literally nothing gets one
    precise message instead of two overlapping ones.

    @brief Measure, log and return index coverage.
    @return The coverage measurement.
    @version 2
    """
    from .doxygen import (
        warn_if_no_function_bodies,
    )

    coverage = measure_index_coverage(Path(db_path), Path(repo_root))
    if not warn_if_no_function_bodies(Path(db_path)):
        _log_coverage(coverage)
    return coverage
