"""The incremental splice must produce what a full rebuild produces. Nothing weaker.

WHY THIS IS AN INVARIANCE AND NOT A COUNT. A count-based test cannot tell a correct splice
from a lossy one that happens to look plausible, and "plausible row count plus a success
message" is this project's signature failure. The measurement that motivated the whole module
makes the point: a subset doxygen run over one changed file recovered 0 of that file's 38
outbound cross-file xrefs AND reported a perfectly sane number of rows. So the control here
is equality against ground truth — rebuild the same tree from scratch and demand the spliced
database agree, member for member and edge for edge.

REAL DOXYGEN, REAL SOURCE. The hermetic suite builds its databases from the pipeline's own
DDL, which cannot test this at all: the whole question is what doxygen does to its OWN output
when the input set changes, and a synthesized fixture would just replay my assumptions about
that. `tests/data/csample` is 21 C files with cross-file calls and headers, which is exactly
the shape where a subset run loses edges.

WHAT WOULD MAKE THIS TEST LIE. If the comparison keyed on rowids it would pass trivially for
the wrong reason, because both databases number their rows independently. It keys on
`refid` TEXT and normalised paths — the identities that survive a rebuild — so a splice that
lands a member on the wrong rowid still fails.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from clew.doxygen import in_doxygen_scope, run_doxygen
from clew.doxygen_splice import (
    include_expansion,
    normalize_path,
    splice_doxygen,
    xref_closure,
)

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).resolve().parent.parent / "data" / "csample"


##
# @brief Write a minimal Doxyfile that indexes one directory tree.
# @param root The repository root to index.
# @param out Where the Doxyfile is written.
# @return The Doxyfile path.
# @version 1
def _doxyfile(root: Path, out: Path) -> Path:
    """Deliberately minimal. `run_doxygen` forces RECURSIVE, EXTRACT_STATIC and the sqlite3
    output, so a target needs only INPUT — and keeping this file bare means the test exercises
    the pipeline's forced flags rather than a hand-tuned configuration.

    @brief Write a bare Doxyfile.
    @return Its path.
    @version 1
    """
    out.write_text(
        f"PROJECT_NAME = splice\nINPUT = {root}\nGENERATE_SQLITE3 = YES\n"
        "EXTRACT_ALL = YES\nREFERENCED_BY_RELATION = YES\nREFERENCES_RELATION = YES\n"
        ## A DECLARED EXCLUDE_PATTERNS, because that is what real targets ship — entropic
        ## declares `*/extern/* */build/* */tests/*`. The tree scan honours EXCLUDE roots but
        ## NOT this glob spelling, so an excluded file still lands in the changed set; and the
        ## subset run emits `EXCLUDE_PATTERNS =` while listing paths individually, which is how
        ## a file a full build never indexes gets spliced INTO the master.
        "EXCLUDE_PATTERNS = */vendor/*\n",
        encoding="utf-8",
    )
    return out


##
# @brief Run doxygen over a whole tree or an explicit subset.
# @param doxyfile The Doxyfile to base the run on.
# @param work Scratch directory that will hold the output.
# @param subset Repo-relative paths to make the whole INPUT, or None for the whole tree.
# @param root The repository root, used to absolutise subset paths.
# @return The generated database path.
# @version 1
def _run(doxyfile: Path, work: Path, root: Path, subset: list[str] | None = None) -> Path:
    """@brief Run doxygen, optionally restricted to a subset.
    @return Path to the generated database.
    @version 1
    """
    work.mkdir(parents=True, exist_ok=True)
    return run_doxygen(
        doxyfile,
        work,
        extra_input=[str(root / p) for p in subset] if subset else None,
        replace_input=bool(subset),
        output_dir=work,
    )


##
# @brief Reduce a doxygen database to the content a rebuild must reproduce.
# @param db The database to read.
# @param root The repository root, for path normalisation.
# @return Members and cross-reference edges as comparable sets.
# @version 1
def _snapshot(db: Path, root: Path) -> dict[str, set]:
    """KEYED ON refid AND NORMALISED PATH, never on rowid. Two independent doxygen runs
    number their rows differently, so a rowid comparison would either pass vacuously or fail
    for a reason that has nothing to do with correctness.

    @brief Snapshot a database's members and edges.
    @return Dict of comparable sets.
    @version 1
    """
    conn = sqlite3.connect(db)
    try:
        members = {
            (normalize_path(str(path), root), str(name), str(kind))
            for path, name, kind in conn.execute(
                "SELECT p.name, md.name, md.kind FROM memberdef md "
                "JOIN path p ON p.rowid = md.file_id"
            )
        }
        edges = {
            (str(src), str(dst), str(ctx))
            for src, dst, ctx in conn.execute(
                "SELECT rs.refid, rd.refid, x.context FROM xrefs x "
                "JOIN refid rs ON rs.rowid = x.src_rowid "
                "JOIN refid rd ON rd.rowid = x.dst_rowid"
            )
        }
        compounds = {
            (normalize_path(str(path), root), str(name), str(kind))
            for path, name, kind in conn.execute(
                "SELECT p.name, cd.name, cd.kind FROM compounddef cd "
                "JOIN path p ON p.rowid = cd.file_id"
            )
        }
        ## ADDED AFTER A MUTATION CONTROL MISSED. Deleting the `_insert_relations` call left
        ## this test green, because the three sets above never read `member` or `contains` —
        ## so the rows that make a class's methods findable AS members were unguarded, which
        ## is the "test for the failure path and none for the success path" shape this repo
        ## keeps shipping.
        relations = {
            ("member", str(left), str(right))
            for left, right in conn.execute(
                "SELECT rl.refid, rr.refid FROM member m "
                "JOIN refid rl ON rl.rowid = m.scope_rowid "
                "JOIN refid rr ON rr.rowid = m.memberdef_rowid"
            )
        } | {
            ("contains", str(left), str(right))
            for left, right in conn.execute(
                "SELECT rl.refid, rr.refid FROM contains c "
                "JOIN refid rl ON rl.rowid = c.inner_rowid "
                "JOIN refid rr ON rr.rowid = c.outer_rowid"
            )
        }
        ## EVERY REMAINING TABLE `_delete_file_rows` TOUCHES. Four of them were deleted per
        ## changed file and never re-inserted, and this snapshot could not see it because it
        ## compared only members / compounds / xrefs / member+contains. Keyed on refid or on
        ## path name so two independent builds are comparable.
        params = {
            (str(md), str(ptype or ""), str(pname or ""))
            for md, ptype, pname in conn.execute(
                "SELECT r.refid, p.type, p.declname FROM memberdef_param mp "
                "JOIN memberdef m ON m.rowid = mp.memberdef_id "
                "JOIN refid r ON r.rowid = m.rowid "
                "JOIN param p ON p.rowid = mp.param_id"
            )
        }
        reimpl = {
            (str(a), str(b))
            for a, b in conn.execute(
                "SELECT ra.refid, rb.refid FROM reimplements x "
                "JOIN refid ra ON ra.rowid = x.memberdef_rowid "
                "JOIN refid rb ON rb.rowid = x.reimplemented_rowid"
            )
        }
        bases = {
            (str(a), str(b))
            for a, b in conn.execute(
                "SELECT ra.refid, rb.refid FROM compoundref x "
                "JOIN refid ra ON ra.rowid = x.base_rowid "
                "JOIN refid rb ON rb.rowid = x.derived_rowid"
            )
        }
        ## THE INDEXED FILE SET. The general guard for scope: whatever the splice does, the
        ## set of files doxygen actually PROCESSED must equal what a full rebuild processes.
        ## `compounddef` of kind 'file' is that set — a `path` row also exists for unresolved
        ## includes, which legitimately differ between runs.
        indexed = {
            normalize_path(str(name), root)
            for (name,) in conn.execute(
                "SELECT p.name FROM compounddef cd JOIN path p ON p.rowid = cd.file_id "
                "WHERE cd.kind = 'file'"
            )
        }
        ## NAME-KEYED EDGES, alongside the refid-keyed set. refids are HASHED
        ## (`main_8c_1a9f...`), so no assertion about a particular function can match on the
        ## refid text — a gate that tried found nothing and reported the rebuild had no edge.
        ## Names are also what a reader of a failure message can act on.
        named_edges = {
            (str(a), str(b))
            for a, b in conn.execute(
                "SELECT cs.name, cd.name FROM xrefs x "
                "JOIN memberdef cs ON cs.rowid = x.src_rowid "
                "JOIN memberdef cd ON cd.rowid = x.dst_rowid"
            )
        }
        incl = {
            (normalize_path(str(a), root), normalize_path(str(b), root))
            for a, b in conn.execute(
                "SELECT s.name, d.name FROM includes i "
                "JOIN path s ON s.rowid = i.src_id JOIN path d ON d.rowid = i.dst_id"
            )
        }
    finally:
        conn.close()
    return {
        "members": members,
        "edges": edges,
        "compounds": compounds,
        "relations": relations,
        "params": params,
        "reimplements": reimpl,
        "compoundref": bases,
        "includes": incl,
        "named_edges": named_edges,
        "indexed": indexed,
    }


##
# @brief The files the test edits, and the edits themselves.
# @param root The copied fixture root.
# @return The repo-relative paths that were modified.
# @version 2
def _make_edit(root: Path) -> set[str]:
    """TWO FILES, EACH TARGETING A DIFFERENT TABLE, and the second exists because a mutation
    control caught the first version being vacuous.

    `main.c` gets a cross-file CALL, which is the case a subset run gets wrong — a whitespace
    or comment change would be re-read identically by both paths and prove nothing.

    `shapes.cpp` gets a second DERIVED CLASS overriding the virtual, because
    `reimplements`/`compoundref` rows only need restoring for a file that CHANGED. With only
    `main.c` edited, those tables were compared but the changed file contributed nothing to
    them, so deleting their restoration left this test green — the non-vacuity gate below
    confirmed the tables were non-empty GLOBALLY and still could not see it. An invariance is
    only load-bearing for a table the CHANGED SET actually populates.

    @brief Edit one C file for edges and one C++ file for inheritance.
    @return The edited files' repo-relative paths.
    @version 2
    """
    ## A NEW CROSS-FILE CALL TO A FUNCTION THAT ACTUALLY EXISTS. The previous version called
    ## `sound_service_init()`, which the fixture declares NOWHERE — so no edge existed in the
    ## rebuild either and the comparison was vacuous for exactly the case the closure is meant
    ## to protect. `sound_play_findme` is declared in src/sound/sound_service.h and `main.c`
    ## did not call it, so this edit introduces a call whose callee's file was NOT in the
    ## pre-edit xref table — which is the shape a closure computed from the OLD master misses.
    ## The added `#include` exercises the includes restoration at the same time.
    main = root / "src" / "main.c"
    main.write_text(
        main.read_text(encoding="utf-8").replace(
            '#include "telemetry/telemetry.h"',
            '#include "telemetry/telemetry.h"\n#include "sound/sound_service.h"',
            1,
        )
        + "\n\nvoid splice_probe_added(void)\n{\n    sound_play_findme(1);\n}\n",
        encoding="utf-8",
    )
    shapes = root / "src" / "shapes.cpp"
    shapes.write_text(
        shapes.read_text(encoding="utf-8")
        + "struct Extra : Base { int area() const override; };\n"
        + "int Extra::area() const { return 2; }\n",
        encoding="utf-8",
    )
    ## The vendored file is EDITED TOO. The tree scan does not know it is excluded, so it
    ## enters the changed set — which is exactly the path by which the splice indexes it.
    vendored = root / "vendor" / "third_party.c"
    vendored.write_text(
        vendored.read_text(encoding="utf-8") + "int vendored_added(void) { return 8; }\n",
        encoding="utf-8",
    )
    return {"src/main.c", "src/shapes.cpp", "vendor/third_party.c"}


##
# @brief A spliced database must equal a full rebuild of the same tree.
# @param tmp_path Pytest scratch directory.
# @return None.
# @version 1
def test_incremental_splice_matches_a_full_rebuild(tmp_path: Path) -> None:
    """THE LOAD-BEARING CONTROL for task #483.

    @brief Splice output equals rebuild output.
    @return None.
    @version 1
    """
    root = tmp_path / "repo"
    shutil.copytree(FIXTURE, root)
    ## THE C FIXTURE HOLDS ZERO `reimplements` AND `compoundref` ROWS, so an invariance over
    ## those tables would pass vacuously on it — 0 == 0. A base/derived pair with a virtual
    ## override is the smallest thing that populates both, and without it the review's
    ## least-measured finding stays unmeasured.
    (root / "src" / "shapes.cpp").write_text(
        "struct Base { virtual int area() const; virtual ~Base() {} };\n"
        "struct Derived : Base { int area() const override; };\n"
        "int Base::area() const { return 0; }\n"
        "int Derived::area() const { return 1; }\n",
        encoding="utf-8",
    )
    ## A real C file inside a directory the Doxyfile EXCLUDES by glob. A full rebuild must
    ## never index it; the splice must not either.
    (root / "vendor").mkdir(parents=True, exist_ok=True)
    (root / "vendor" / "third_party.c").write_text(
        "int vendored_helper(void) { return 7; }\n", encoding="utf-8"
    )
    doxyfile = _doxyfile(root, tmp_path / "Doxyfile")

    master = _run(doxyfile, tmp_path / "master", root)
    master_kept = tmp_path / "master-kept.db"
    shutil.copy2(master, master_kept)

    ## THE SAME SCOPE FILTER THE PIPELINE APPLIES. `_make_edit` also touches a file the
    ## Doxyfile excludes by glob, because the tree scan cannot see that exclusion — narrowing
    ## here is what keeps the splice from indexing a file no full rebuild produces.
    changed = set(in_doxygen_scope(sorted(_make_edit(root)), doxyfile, True))

    truth = _run(doxyfile, tmp_path / "truth", root)
    truth_kept = tmp_path / "truth-kept.db"
    shutil.copy2(truth, truth_kept)

    subset = sorted(xref_closure(master_kept, changed, root))
    assert changed <= set(subset), "the closure must contain the changed set itself"
    assert len(subset) < len(list(root.rglob("*.c"))) + len(list(root.rglob("*.h"))), (
        "the closure expanded to the whole tree, so this test would pass without "
        "exercising any subsetting at all"
    )

    subset_db = _run(doxyfile, tmp_path / "subset", root, subset=subset)

    ## SECOND PASS. The first subset is built from the PRE-EDIT xref table, so it cannot know
    ## about a callee the edit newly calls. `include_expansion` reads the first pass's include
    ## graph — doxygen's own resolution, not a regex — and names the files that graph implies.
    extra = include_expansion(subset_db, master_kept, changed, set(subset), root)
    if extra:
        subset = sorted(set(subset) | extra)
        subset_db = _run(doxyfile, tmp_path / "subset2", root, subset=subset)
    spliced = tmp_path / "spliced.db"
    report = splice_doxygen(master_kept, subset_db, changed, spliced, root)

    assert not report.skipped, f"splice skipped files: {report.skipped}"
    assert report.files_replaced >= 2
    assert report.members_inserted > 0, "no members inserted — the splice did nothing"
    assert report.relations_dropped == 0, (
        "a relation endpoint was missing from the working copy, which means the closure did "
        "not bring in a compound the subset needed"
    )
    assert report.compounds_inserted > 0, (
        "no compounddefs inserted while some were deleted — every class, struct and "
        "file-compound in the changed file would be silently lost"
    )

    got = _snapshot(spliced, root)
    want = _snapshot(truth_kept, root)

    ## NON-VACUITY GATE. An invariance over an EMPTY table passes as 0 == 0 and proves nothing.
    ## The C fixture holds no inheritance at all, which is why `shapes.cpp` is written into the
    ## copy — and this asserts that it worked. Without this gate, deleting the reimplements and
    ## compoundref restoration would leave the comparison green.
    for layer in ("params", "reimplements", "compoundref", "includes"):
        assert want[layer], (
            f"the rebuild produced NO {layer} rows, so comparing that table is vacuous and "
            f"the splice could drop it undetected — the fixture needs to populate it"
        )
    ## AND THE CHANGED SET MUST CONTRIBUTE TO THEM. Global non-emptiness is not enough: with
    ## only `main.c` edited, reimplements and compoundref were non-empty yet came entirely from
    ## an UNCHANGED file, so their rows were never deleted and deleting their restoration was
    ## invisible. Two mutation controls passed against that shape.
    ## `Extra` is the class the edit ADDS to shapes.cpp, and doxygen keys a class member's
    ## refid to the CLASS compound (`structExtra_...`), never to the file — so keying this gate
    ## on the file name silently found nothing. Its compounddef's `file_id` IS shapes.cpp, so
    ## the splice deletes it and must put it back.
    for layer in ("reimplements", "compoundref"):
        assert any("Extra" in ref for row in want[layer] for ref in row), (
            f"no {layer} row involves the class the edit added, so that table is compared but "
            f"never exercised by the splice's delete path — two mutation controls passed "
            f"against exactly that shape"
        )

    added = [m for m in got["members"] if m[1] == "splice_probe_added"]
    assert added, "the edit's new function is absent from the spliced database"

    ## THE NEW CROSS-FILE EDGE, PINNED BY NAME. The set comparison below would catch its
    ## absence too, but only as one line among many — and this exact edge is what the closure
    ## exists to preserve, so it gets its own assertion with its own message.
    ## SCOPE NON-VACUITY. If the rebuild indexed the vendored file too, the exclusion is not
    ## in force and the scope comparison below proves nothing.
    assert not any("vendor/" in f for f in want["indexed"]), (
        f"the full rebuild indexed the excluded vendor/ tree, so EXCLUDE_PATTERNS is not "
        f"taking effect and this test cannot see a scope widening: "
        f"{sorted(f for f in want['indexed'] if 'vendor' in f)}"
    )

    probe = ("splice_probe_added", "sound_play_findme")
    assert probe in want["named_edges"], (
        f"the rebuild produced no {probe[0]} -> {probe[1]} edge, so this test cannot see "
        f"whether the splice preserves a NEWLY-ADDED cross-file call at all"
    )
    assert probe in got["named_edges"], (
        f"the splice lost the new cross-file edge {probe[0]} -> {probe[1]}. The outbound "
        f"closure is computed from the PRE-EDIT master, where this call did not exist, so "
        f"{probe[1]}'s file never joined the subset and doxygen could not resolve the name"
    )

    for layer in (
        "members",
        "compounds",
        "edges",
        "relations",
        "params",
        "reimplements",
        "compoundref",
        "includes",
        "named_edges",
        "indexed",
    ):
        missing = want[layer] - got[layer]
        extra = got[layer] - want[layer]
        assert not missing and not extra, (
            f"{layer}: splice and rebuild disagree.\n"
            f"  missing from splice ({len(missing)}): {sorted(missing)[:8]}\n"
            f"  only in splice ({len(extra)}): {sorted(extra)[:8]}"
        )
