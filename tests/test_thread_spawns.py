# SPDX-License-Identifier: MIT
"""C/C++ spawn-primitive coverage: which platforms the DEFAULT pattern set can see.

WHY THIS FILE EXISTS. `DEFAULT_SPAWN_PATTERNS` had no Windows entry at all, and the thread
roster simultaneously told its reader to "Quote origin.first_party as the repository's thread
count". So a Win32 codebase's threads were invisible while the payload presented the number as
complete — and on Mbed-TLS/mbedtls that shipped a measured falsehood into a graded answer: 1
reported against 2 real, the missing one being `_beginthread(TimerProc, 0, NULL)`.

The Python side of the same layer has `tests/test_python_ast.py`; the C side had no test for
which primitives are covered, only for how a matched one is resolved. That asymmetry is what
let a whole platform stay missing.

@brief Tests for C/C++ thread-spawn pattern coverage.
@version 1
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from clew.harvest import _cached_parser, try_import_tree_sitter
from clew.threads import (
    DEFAULT_SPAWN_PATTERNS,
    _walk_spawn_sites,
    load_thread_patterns,
)
from clew.vocabulary import THREAD_KIND, THREAD_KIND_WIN32

pytestmark = pytest.mark.skipif(
    try_import_tree_sitter() is None,
    reason="the spawn-pattern tests need tree_sitter + its C/C++ grammars",
)


## @brief Parse C source into a tree-sitter tree.
## @param src The source bytes.
## @return (tree, src_bytes).
## @version 1
def _parse_c(src: bytes) -> tuple[Any, bytes]:
    """REUSES `_cached_parser` rather than rebuilding the parser here, and that is not just
    tidiness: `try_import_tree_sitter` returns `(Language, Parser)` — Language FIRST — and a
    hand-rolled `Parser(Language(mod.language()))` with the tuple unpacked the other way round
    fails with `argument 1 must be tree_sitter.Language, not PyCapsule`. One construction site
    cannot get the order wrong in two places.

    @brief Build a C parse tree for a source snippet.
    @return The tree and the bytes it was built from.
    @version 2
    """
    imported = try_import_tree_sitter()
    assert imported is not None
    language_cls, parser_cls = imported
    parser = _cached_parser("tree_sitter_c", {}, parser_cls, language_cls)
    assert parser is not None, "the C grammar must be importable"
    return parser.parse(src), src


## The three Windows spawns beside the POSIX one, in ONE fixture. Separate fixtures would let a
## broken Windows pattern pass while POSIX still worked, which is exactly the failure shape
## gh#11 taught: write the negative half, in the same file, so a fix cannot silently trade one
## capability for another.
##
## THE ARGUMENT POSITIONS ARE THE POINT. `_beginthread` takes the entry FIRST;
## `_beginthreadex` and `CreateThread` take it THIRD, behind a security pointer and a stack
## size. Each call below therefore puts a NON-ENTRY value where a naive index-0 pattern would
## look, so a wrong index harvests `0`/`NULL`/`stack` rather than the function.
_WIN_AND_POSIX = b"""\
static void TimerProc(void *arg) { (void) arg; }
static unsigned __stdcall WorkerProc(void *arg) { (void) arg; return 0; }
static void *PosixProc(void *arg) { return arg; }

void boot(void)
{
    (void) _beginthread(TimerProc, 0, NULL);
    (void) _beginthreadex(NULL, 0, &WorkerProc, NULL, 0, NULL);
    (void) CreateThread(NULL, 0, WorkerProc, NULL, 0, NULL);
    pthread_create(&tid, NULL, PosixProc, NULL);
}
"""


## @brief Every Windows spawn primitive is covered, and POSIX still is.
## @return None.
## @version 1
def test_windows_spawns_are_harvested_and_posix_still_is() -> None:
    """The two-sided assertion. Adding a platform must not cost the one already working, and a
    test that only checked the new rows would not notice if it had.

    @brief All four spawn sites resolve to their own entry function.
    @version 1
    """
    patterns = {p.name: p for p in load_thread_patterns(None)}
    tree, src = _parse_c(_WIN_AND_POSIX)
    sites = _walk_spawn_sites(tree, src, patterns)

    entries = sorted(site[1] for site in sites)
    assert entries == ["PosixProc", "TimerProc", "WorkerProc", "WorkerProc"], (
        f"expected all four spawn sites, got {entries}"
    )


## @brief The entry index differs per primitive, and a wrong one is caught rather than plausible.
## @return None.
## @version 1
def test_the_entry_argument_position_is_read_per_primitive() -> None:
    """THE ASSERTION THAT GROUNDING EARNED. My own plan said all three Windows primitives had
    "the shape of std::thread exactly, entry_arg_index=0". That is true of `_beginthread` ONLY:

        _beginthread( start_address, stack_size, arglist )                   -> 0
        _beginthreadex( security, stack_size, start_address, arglist, ... )  -> 2
        CreateThread( lpThreadAttributes, dwStackSize, lpStartAddress, ... ) -> 2

    Read off the documented signatures rather than recalled, and index 0 additionally confirmed
    against the real mbedtls call site. Shipping index 0 for all three would have harvested
    `NULL` or `0` as the entry — a GARBAGE thread row, which is worse than no row, because a
    missing row is visible as absence while a wrong one is quoted.

    Asserted on the PATTERN TABLE and not only through the walker, because the walker's failure
    on a bad index is a silently different entry name rather than an error.

    @brief Each Windows primitive declares the entry index its real signature has.
    @version 1
    """
    by_name = {p.name: p for p in DEFAULT_SPAWN_PATTERNS}
    assert by_name["_beginthread"].entry_arg_index == 0
    assert by_name["_beginthreadex"].entry_arg_index == 2, (
        "the entry is behind `security` and `stack_size`; index 0 would harvest NULL"
    )
    assert by_name["CreateThread"].entry_arg_index == 2, (
        "the entry is behind `lpThreadAttributes` and `dwStackSize`"
    )
    ## None of the three carries a thread NAME argument, so the row is named by its entry.
    for name in ("_beginthread", "_beginthreadex", "CreateThread"):
        assert by_name[name].name_arg_index is None, f"{name} has no name argument"
        assert by_name[name].kind == THREAD_KIND_WIN32, (
            f"{name} is a Win32 thread — labelling it 'pthread' asserts a POSIX primitive that "
            f"is not there, and 'task' asserts an RTOS work item"
        )


## @brief `win32` is a real vocabulary member, so the CHECK constraint admits it.
## @return None.
## @version 1
def test_the_win32_kind_is_admitted_by_the_vocabulary() -> None:
    """A pattern whose `kind` the CHECK rejects fails at INSERT — after a full parse — so the
    cost of getting this wrong is a build that dies late rather than a pattern that is ignored.
    `THREAD_KIND.validated` is what `load_thread_patterns` routes a declared kind through, and
    a value in `values` but missing from `rank` raises on a payload path rather than at import,
    which is why both now derive from one tuple.

    @brief The win32 kind validates and ranks.
    @version 1
    """
    assert THREAD_KIND_WIN32 in THREAD_KIND.values
    assert THREAD_KIND_WIN32 in THREAD_KIND.rank, (
        "`values` and `rank` were two hand-maintained copies; a member in one and not the "
        "other is a KeyError waiting on a payload path"
    )
    assert (
        THREAD_KIND.validated(THREAD_KIND_WIN32, owner="probe", field="kind") == THREAD_KIND_WIN32
    )


## @brief A declared pattern can still override a Windows default.
## @return None.
## @version 1
def test_a_declaration_still_overrides_a_windows_default(tmp_path: Any) -> None:
    """Defaults must stay overridable. A project that wraps `CreateThread` behind its own
    signature has to be able to say so, and `load_thread_patterns` merges a declared entry OVER
    a default of the same name.

    @brief A declared entry replaces the built-in Windows pattern.
    @version 1
    """
    manifest = tmp_path / "spawns.yaml"
    manifest.write_text(
        "spawns:\n  - name: CreateThread\n    entry_arg_index: 0\n    kind: task\n",
        encoding="utf-8",
    )
    by_name = {p.name: p for p in load_thread_patterns(manifest)}
    assert by_name["CreateThread"].entry_arg_index == 0, "the declaration must win"
    assert by_name["CreateThread"].kind == "task"
    ## And the other defaults survive the merge.
    assert by_name["_beginthread"].entry_arg_index == 0
    assert by_name["pthread_create"].entry_arg_index == 2


## @brief The spawn hint finds a repo's OWN wrapper and is honest about what it cannot see.
## @param tmp_path pytest temp dir.
## @return None.
## @version 1
def test_the_spawn_hint_finds_a_declared_wrapper_and_not_an_external_api(tmp_path: Any) -> None:
    """THE NEGATIVE HALF IS THE POINT OF THIS TEST, and it was found by running the hint against
    its own motivating case rather than by believing it.

    `detect_undeclared_spawn_primitives` reads `memberdef` — the names this repository DECLARES.
    Asked what a build with no Windows coverage was missing on real mbedtls, it returns
    `thread_create` and NOT `_beginthread`, because `_beginthread` lives in `<process.h>` and
    mbedtls only CALLS it. So the hint could not have found the gap it exists for.

    The lock hint escapes the same limit only because mbedtls declares `mbedtls_mutex_lock`
    itself as an extern pointer in its own header. That asymmetry is a property of the two
    repositories, not of the two detectors — which is exactly why assuming the lock hint's
    success would transfer was worth checking.

    Pinned here so the limit cannot be quietly forgotten and the payload cannot drift back into
    promising a hint this class of primitive can never produce.

    @brief A declared wrapper is hinted; an only-called external API is not.
    @version 1
    """
    import sqlite3

    from clew.threads import detect_undeclared_spawn_primitives

    conn = sqlite3.connect(":memory:")
    ## `kind` IS PART OF THE WORLD AND WAS MISSING HERE. `detect_undeclared_spawn_primitives`
    ## now restricts to callable kinds, and a fixture without the column cannot exercise that —
    ## it would report green against no filter at all, which is this module's own recorded
    ## failure shape one turn later.
    conn.execute("CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, name TEXT, kind TEXT)")
    conn.executemany(
        "INSERT INTO memberdef (name, kind) VALUES (?, ?)",
        [
            ("sys_thread_create", "function"),  # the repo's OWN wrapper — declared, findable
            ("thread_local_slot", "function"),  # subject word, no creation verb -> noise
            ("CreateFileA", "function"),  # creation verb, no subject word -> noise
            ("pthread_mutex_lock", "function"),  # contains "thread", not a spawn at all
            ## THE FOUR NOISE NAMES BELOW ARE REAL, COPIED FROM THIS REPO'S OWN INDEX, and they
            ## are here because the first version of the heuristic named all of them. It asked
            ## for a subject word AND a verb ANYWHERE in the name, which prose satisfies
            ## trivially — clew's index produced SIX such candidates, every one a test
            ## function. The curated four above all passed while the detector was 100% noise on
            ## the first real corpus it saw: the fixture matched the detector, not the world.
            ("test_extract_threads_always_creates_empty_tables", "function"),
            ("test_a_null_entry_thread_is_attributed_by_its_spawn_site", "function"),
            ("test_default_spawn_patterns_cover_std_thread", "function"),
            ## `new_thread` IS adjacent, so adjacency alone does not reject this one — the
            ## `test_` prefix term is what does, and it earned its place on this single name.
            ("test_new_thread_kinds_are_registered_in_the_vocabulary", "function"),
            ## AND THE CONVERSE, which makes ADJACENCY load-bearing rather than decorative. All
            ## four real noise names above happen to be `test_`-prefixed, so a mutation that
            ## dropped adjacency entirely left the suite green — the prefix term was doing all
            ## the work and the more general rule was untested. This name is prose with a
            ## subject and a verb far apart and NO test prefix, so only adjacency rejects it.
            ("worker_pool_was_started_by_main", "function"),
        ],
    )
    conn.commit()

    found = detect_undeclared_spawn_primitives(conn, load_thread_patterns(None))
    assert found == ["sys_thread_create"], (
        f"expected only the repo's own wrapper, got {found} — a subject word and a creation "
        f"verb are required TOGETHER precisely so this list stays short enough to act on"
    )

    ## AND THE LIMIT: an external API present only as a CALL, never as a declared name, cannot
    ## be hinted at. `_beginthread` is absent from `memberdef` above exactly as it is absent
    ## from mbedtls's.
    assert "_beginthread" not in found, (
        "if this ever starts passing, the detector has gained a call-site source and the "
        "payload's hedge about only-called APIs should be revisited"
    )

    ## A COVERED primitive is never re-suggested, including one matched by its dotted tail —
    ## otherwise every Python default would leave its own primitive looking undeclared.
    conn.execute("INSERT INTO memberdef (name) VALUES ('xTaskCreate')")
    conn.execute("INSERT INTO memberdef (name) VALUES ('Thread')")
    conn.commit()
    covered = detect_undeclared_spawn_primitives(conn, load_thread_patterns(None))
    assert "xTaskCreate" not in covered, "a default-covered primitive must not be suggested"


## @brief The target's OWN doc scope is recorded, and absence stays absent.
## @param tmp_path pytest temp dir.
## @return None.
## @version 1
def test_the_targets_declared_doc_scope_is_recorded_not_ours(tmp_path: Any) -> None:
    """INDEX SCOPE IS NOT DOXYFILE SCOPE, and until now only the first was recorded. The
    pipeline reads a target's Doxyfile for ALIASES and PREDEFINED and deliberately REPLACES its
    INPUT, so nothing in the index could answer what the repository itself chooses to document
    — `FILE_PATTERNS = *.h` means an API reference over headers only, and that is a different
    claim from what we indexed.

    The cost was already recorded in `write_build_signature`'s own docstring: on the entropic
    grid the raw arm scored 3/3 on "checks the Doxyfile and reports that its INPUT does not
    list examples/" and the index arm 1/3, the only clearly actionable gap in 56 marks.
    Persisting our scope fixed the half about OUR boundary and left the half about THEIRS.

    THE STATED PATH IS WHAT MAKES IT REACHABLE. Discovery refuses to guess — root, then
    `docs/`/`doc/`, then nothing — so Mbed-TLS's `doxygen/mbedtls.doxyfile` is invisible to it
    and this section would stay empty on the one target the question is asked about.

    AND ABSENCE MUST STAY ABSENT: a repo that declares no doc scope records no keys, because
    "not recorded" and "recorded as doxygen's default" are different claims. `declared_file_patterns`
    was written for exactly this and returns empty rather than the defaults — it existed, was
    kept deliberately, and was read by nobody.

    @brief The declared doc scope is recorded from the target's own Doxyfile, or not at all.
    @version 1
    """
    from clew.cli import _doxyfile_scope

    root = tmp_path
    doxyfile = tmp_path / "doxygen" / "project.doxyfile"
    doxyfile.parent.mkdir()
    doxyfile.write_text(
        "PROJECT_NAME = probe\nINPUT = ../include input\nFILE_PATTERNS = *.h\n"
        "EXCLUDE_PATTERNS = */extern/*\n",
        encoding="utf-8",
    )

    def rel(path: Any) -> str:
        """@brief Repo-relative spelling. @return The relative path. @version 1"""
        return str(Path(path).resolve().relative_to(root))

    got = _doxyfile_scope(root, rel, str(doxyfile))
    assert got["doxyfile_path"] == "doxygen/project.doxyfile"
    assert got["doxyfile_file_patterns"] == "*.h", (
        "the headers-only fact is the whole answer to 'does the doc build cover implementation'"
    )
    assert "../include" in got["doxyfile_input"]
    ## THE THIRD KEY. A scope statement has three and reading one answers less than it looks:
    ## a surviving EXCLUDE_PATTERNS once dropped a submodule from a build that exited 0.
    assert got["doxyfile_excludes"] == "*/extern/*"

    ## NOT RECORDED, not recorded-as-empty, when the repo declares nothing. Discovery finds
    ## nothing at a bare root, and no key may be invented for it.
    assert _doxyfile_scope(tmp_path / "empty", rel, None) == {}


## @brief The vendored signal names only what exists, and counts the rest.
## @param tmp_path pytest temp dir.
## @return None.
## @version 1
def test_vendored_paths_name_only_what_exists_and_report_what_does_not(tmp_path: Any) -> None:
    """D4: `external` STAYS A GIT TREE and this is a separate declared signal. The distinction is
    not pedantry — on Mbed-TLS `3rdparty/` (holding `everest` and `p256-m`) is COMMITTED, not a
    submodule, so `dg_external_root` is correctly NULL across all 570 rows and no git-tree test
    can ever find it. Widening `external` to mean "looks vendored" would move `coverage`,
    `graph_stats` and every orphan count for a naming fashion.

    DECLARED, NOT INFERRED, per the no-hardcoding mandate: one repo keeps it at `3rdparty/`,
    another at `external/` or `deps/`, and a directory named `3rdparty` full of first-party glue
    is a real thing.

    ONLY PATHS THAT EXIST ARE NAMED. gh#335 nearly published a machine path exactly this way —
    the nested-tree walk saw every directory on disk including ones another rule excluded, and
    the first version stamped an excluded target's name into `scope.external_roots`. The rule
    that came out of it is "report only roots that own at least one indexed row; count the
    rest", and a declared path that is simply a TYPO is the same failure: echoing it back as
    though it were found is how a declaration gets believed.

    So the missing half is the actionable half — it distinguishes a repository with no vendored
    code from one whose declaration nobody checked.

    @brief Declared vendored paths are split into present and missing.
    @version 1
    """
    import argparse

    from clew.cli import _vendored_scope

    real = tmp_path / "3rdparty"
    (real / "everest").mkdir(parents=True)

    def rel(path: Any) -> str:
        """@brief Repo-relative spelling. @return The relative path. @version 1"""
        return str(Path(path).resolve().relative_to(tmp_path))

    args = argparse.Namespace(guard_config=None, vendored=["3rdparty", "thirdparty_typo"])
    got = _vendored_scope(tmp_path, rel, args)

    assert got["vendored_roots"] == "3rdparty", "only the path that EXISTS may be named"
    assert got["vendored_declared_missing"] == "thirdparty_typo", (
        "a declared path that matches nothing is a FINDING, not a no-op — it is the "
        "difference between no vendored code and an unchecked declaration"
    )
    ## What was asked for is kept beside what was found, so the two cannot be confused.
    assert got["vendored_declared"] == "3rdparty, thirdparty_typo"

    ## NOT RECORDED when nothing is declared. Absence must not read as "no vendored code".
    assert (
        _vendored_scope(tmp_path, rel, argparse.Namespace(guard_config=None, vendored=None)) == {}
    )


## @brief `vendored` is a real declaration section AND a statable option.
## @return None.
## @version 1
def test_vendored_is_reachable_from_both_declaration_tiers() -> None:
    """A DECLARATION REACHABLE ONLY FROM ONE TIER IS HALF A DECLARATION, and this repo's own
    recorded lesson is the sharper form: "a declaration reachable only from argv is not a
    declaration". It bites hardest on the case this signal exists for — a third-party repository
    that must stay byte-identical cannot carry a `.clew.yaml`, so tier 1 is the ONLY
    route open to it, and `apply_options` REFUSES an unknown key by name, which is what made
    this wiring necessary rather than optional.

    @brief The section is known to the declaration loader and accepted as an option.
    @version 1
    """
    from clew.buildoptions import INLINE_LIST_OPTIONS, accepted_options
    from clew.declaration import KNOWN_SECTIONS, SECTION_VENDORED

    assert SECTION_VENDORED == "vendored"
    assert SECTION_VENDORED in KNOWN_SECTIONS, "tier 2: a repo's own declaration file"
    assert SECTION_VENDORED in INLINE_LIST_OPTIONS, "tier 1: stated on the call"
    assert SECTION_VENDORED in accepted_options(), (
        "and advertised, or `apply_options` refuses it by name and --declare fails"
    )


## @brief A spawn site records WHO creates the thread, not only where.
## @return None.
## @version 1
def test_the_spawn_site_names_its_enclosing_function() -> None:
    """A COORDINATE WITH NO NAME IS WHY THE AGENT READ THE FILE. Build 35 gave the thread row its
    spawn file and line, so an agent could be told a thread is created at
    `programs/ssl/ssl_pthread_server.c:277` and still have nothing to ask a follow-up ABOUT.
    Measured on mbedtls 2026-08-14: the enclosing function is `thread_create`, whose body holds
    the one shared `mbedtls_ssl_config`, the `pthread_join` and the compile guard — four graded
    marks — and `dossier('thread_create')` already returned all of it. Only the route was absent.

    Verified against the real target after this change: `thread_create` for the pthread spawn at
    `:277`, and `mbedtls_set_alarm` for the `_beginthread` at `programs/test/benchmark.c:430`
    (confirmed by reading the source — the call really does sit in that function).

    FILE SCOPE IS EMPTY, not a placeholder, so a spawn in a static initialiser reads as "no
    enclosing function" rather than naming one that does not exist.
    """
    patterns = {p.name: p for p in load_thread_patterns(None)}
    src = (
        b"#include <pthread.h>\n"
        b"static void *WorkerProc(void *a) { return a; }\n"
        b"int thread_create(void) {\n"
        b"    pthread_t t;\n"
        b"    return pthread_create(&t, NULL, WorkerProc, NULL);\n"
        b"}\n"
        b"void *raced = (void *) 0;\n"
    )
    tree, raw = _parse_c(src)
    sites = _walk_spawn_sites(tree, raw, patterns)

    assert len(sites) == 1, f"expected the one pthread spawn, got {sites}"
    ## The SEVENTH element, and the arity matters: the flattener folds positionally, so a walk
    ## that emitted six would silently drop this for every row.
    assert len(sites[0]) == 7, f"the payload must be a septet, got {len(sites[0])}"
    assert sites[0][6] == "thread_create"

    ## FILE SCOPE: a spawn outside any function must report "" rather than borrow a name.
    file_scope, raw2 = _parse_c(
        b"#include <pthread.h>\n"
        b"static void *P(void *a) { return a; }\n"
        b"pthread_t g;\n"
        b"int ignored = 0;\n"
    )
    assert _walk_spawn_sites(file_scope, raw2, patterns) == []


## @brief A pointer-returning function's sigil does not leak into the recorded name.
## @return None.
## @version 1
def test_the_enclosing_name_strips_a_pointer_return_sigil() -> None:
    """THE TRAP THAT SPLIT ONE MUTEX INTO TWO LOCK ROWS, one layer over. A pointer return type
    puts its `*` INSIDE the declarator, so `void *make_thread(void)` reads as `*make_thread` if
    the text is taken raw — and a name nobody can look up is worse than none, because it looks
    like an answer. `locks.py` learned this on the entropic grid; this is the same read.
    """
    patterns = {p.name: p for p in load_thread_patterns(None)}
    tree, raw = _parse_c(
        b"#include <pthread.h>\n"
        b"static void *WorkerProc(void *a) { return a; }\n"
        b"void *make_thread(void) {\n"
        b"    pthread_t t;\n"
        b"    pthread_create(&t, NULL, WorkerProc, NULL);\n"
        b"    return (void *) 0;\n"
        b"}\n"
    )
    sites = _walk_spawn_sites(tree, raw, patterns)
    assert len(sites) == 1
    assert sites[0][6] == "make_thread", f"the sigil leaked: {sites[0][6]!r}"


## @brief A spawn primitive is callable; a variable that names one is not a candidate.
## @return None.
## @version 1
def test_the_spawn_diagnostic_ignores_non_callable_symbols() -> None:
    """MEASURED ON THREE BUILT INDEXES, not imagined. `detect_undeclared_spawn_primitives` read
    `SELECT DISTINCT name FROM memberdef` with NO kind filter, so every name in the database was a
    candidate and only `_spawn_shaped` adjacency stood between a constant and a hint:

      * clew's own index reported `_THREAD_SPAWNER_COLUMNS` — kind `variable`, a SQL
        column-list constant in `query/symbols.py`. `THREAD` and `SPAWNER` are adjacent, so shape
        cannot reject it. A spawn primitive is never a variable.
      * a firmware index reported outcome codes shaped like `CREATE_THREAD_ERROR` and
        `CREATE_THREAD_FAILED` beside the genuine wrappers they belong to. Those spellings and
        `SYSTEM_TASKCREATE` are ILLUSTRATIVE — the measurement was taken on a private target and
        its symbol names are not published here.

    THIS FIXES THE FIRST CLASS ONLY, and the boundary is worth stating: a primitive is a
    `function` or a `macro definition` — a wrapper macro like `xTaskCreate` is real and must stay
    — so the error-code macros share a kind with the real ones and NO kind filter can separate
    them. The rule that would is an outcome-suffix blocklist, which is what this detector's own
    docstring argues against, so it is filed rather than shipped.

    THE FIXTURE NOW CARRIES `kind`, which the old one did not. That omission is the same shape
    this module already records against itself: a fixture without the column the world has cannot
    exercise a filter on it, and would have reported this test green against no filter at all.

    @brief Non-callable symbols are not spawn-primitive candidates.
    @return None.
    @version 1
    """
    import sqlite3

    from clew.threads import detect_undeclared_spawn_primitives, load_thread_patterns

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, name TEXT, kind TEXT)")
    conn.executemany(
        "INSERT INTO memberdef (name, kind) VALUES (?, ?)",
        [
            ("sys_thread_create", "function"),
            ("SYSTEM_TASKCREATE", "macro definition"),
            ## The real false positive, verbatim from this repository's own index.
            ("_THREAD_SPAWNER_COLUMNS", "variable"),
            ("thread_create_fn_t", "typedef"),
            ("THREAD_CREATE_RESULT", "enumeration"),
        ],
    )
    conn.commit()

    found = detect_undeclared_spawn_primitives(conn, load_thread_patterns(None))
    assert found == ["SYSTEM_TASKCREATE", "sys_thread_create"], (
        f"a spawn primitive is callable — a function or a wrapper macro. Got {found}; a variable, "
        f"typedef or enumeration that merely NAMES threading is a constant, not a primitive an "
        f"operator can declare"
    )
