# SPDX-License-Identifier: MIT
"""R1 semantic-richness tests: threads, membership, terminus, dispatch_mode,
thread-boundary flags, and declared edge_triggered.

Unit-level like the rest of the suite: synthetic C sources parsed by
tree-sitter against hand-built doxygen-shaped DBs (memberdef/path[/call_edges]),
no heavy doxygen rebuild.

@brief R1 richness layer tests (threads / boundaries / dispatch / terminus).
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.callback_edges import import_callback_registration_edges
from clew.shared_key_edges import (
    import_mqtt_dispatch_edges,
    import_shared_key_edges_declared,
    import_shared_key_edges_inferred,
)
from clew.threads import (
    DEFAULT_SPAWN_PATTERNS,
    _boundary_flags,
    _qualified_at_boundary,
    annotate_thread_boundaries,
    extract_threads,
    load_thread_patterns,
)
from clew.vocabulary import DeclarationError


## @brief `_qualified_at_boundary` accepts only real token matches, both sides.
## @version 1
def test_qualified_at_boundary_rejects_prefix_and_suffix_collisions() -> None:
    """Guards the qualified thread-entry resolver against borrowing another
    class's rowid. A match must be delimited on BOTH sides — rejecting a bad
    prefix (`Owner::run` inside `CoOwner::run`) AND a bad suffix (inside a param
    type `Owner::run_t`), while still accepting the real method (even when its
    own def also mentions the qualified name in a param).

    @brief Both-sided boundary check rejects prefix/suffix collisions.
    @version 1
    """
    accept = [
        ("void LinkOwner::rx_loop()", "LinkOwner::rx_loop"),
        ("void Owner::run(Owner::run_t x)", "Owner::run"),  # real method + param mention
        ("auto Owner::run<int>()", "Owner::run"),  # template
        ("void Owner::run", "Owner::run"),  # end-of-string decl
        ("void CoOwner::run(Owner::run x)", "Owner::run"),  # a real Owner::run param exists
    ]
    reject = [
        ("void CoOwner::run()", "Owner::run"),  # prefix collision
        ("void CoOwner::run(Owner::run_t x)", "Owner::run"),  # the fixed bug: suffix in param type
        ("void Owner::running()", "Owner::run"),  # suffix collision
    ]
    for defn, q in accept:
        assert _qualified_at_boundary(defn, q) is True, (defn, q)
    for defn, q in reject:
        assert _qualified_at_boundary(defn, q) is False, (defn, q)


## @brief Seed a doxygen-shaped memberdef/path[/call_edges] DB for R1 tests.
## @version 1
def _make_db(
    tmp_path: Path,
    functions: list[tuple[int, str, int, int]],
    rel_path: str = "src/foo.c",
    call_edges: list[tuple[int, int]] | None = None,
) -> Path:
    """functions: (rowid, name, bodystart, bodyend), all in one file (file_id=1,
    bodyfile_id=1). call_edges: (caller_rowid, callee_rowid) inserted as
    non-fuzzy 'ast'/'resolved' rows when provided.

    @brief Build a synthetic doxygen-shaped DB for R1 unit tests.
    @version 1
    """
    db_path = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE path (name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY,
            kind TEXT, name TEXT, file_id INTEGER, bodyfile_id INTEGER,
            bodystart INTEGER, bodyend INTEGER
        );
        """,
    )
    conn.execute("INSERT INTO path (rowid, name) VALUES (1, ?)", (rel_path,))
    conn.executemany(
        "INSERT INTO memberdef "
        "(rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend) "
        "VALUES (?, 'function', ?, 1, 1, ?, ?)",
        functions,
    )
    if call_edges is not None:
        conn.execute(
            """
            CREATE TABLE call_edges (
                caller_rowid INTEGER, callee_rowid INTEGER,
                source TEXT, confidence TEXT
            )
            """,
        )
        conn.executemany(
            "INSERT INTO call_edges (caller_rowid, callee_rowid, source, "
            "confidence) VALUES (?, ?, 'ast', 'resolved')",
            call_edges,
        )
    conn.commit()
    conn.close()
    return db_path


# ─── threads: spawn harvest ──────────────────────────────────────────────────


def test_default_spawn_patterns_cover_primitives() -> None:
    names = {p.name for p in DEFAULT_SPAWN_PATTERNS}
    assert {"pthread_create", "xTaskCreate", "osThreadNew"} <= names
    pthread = next(p for p in DEFAULT_SPAWN_PATTERNS if p.name == "pthread_create")
    assert pthread.entry_arg_index == 2
    assert pthread.name_arg_index is None
    assert pthread.kind == "pthread"


def test_load_thread_patterns_merges_overrides(tmp_path: Path) -> None:
    manifest = tmp_path / "spawns.yaml"
    manifest.write_text(
        "spawns:\n"
        "  - name: SYSTEM_TASKCREATE\n"
        "    entry_arg_index: 0\n"
        "    name_arg_index: 1\n"
        "    kind: task\n",
    )
    patterns = load_thread_patterns(manifest)
    by_name = {p.name: p for p in patterns}
    # Built-in primitives still present + the declared wrapper added.
    assert "pthread_create" in by_name
    tc = by_name["SYSTEM_TASKCREATE"]
    assert tc.entry_arg_index == 0
    assert tc.name_arg_index == 1
    assert tc.kind == "task"


def test_extract_threads_pthread_uses_entry_name(tmp_path: Path) -> None:
    """pthread_create carries no name literal — the thread name is the entry
    function's own identifier, entry arg at index 2."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.c").write_text(
        "void worker_entry(void *a) { (void)a; }\n"
        "void boot(void) {\n"
        "    pthread_create(&tid, 0, worker_entry, 0);\n"
        "}\n",
    )
    db = _make_db(
        tmp_path,
        [(1, "worker_entry", 1, 1), (2, "boot", 2, 4)],
        call_edges=[],
    )
    extract_threads(db, tmp_path, None)
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT name, entry_memberdef_rowid, kind, source, confidence FROM threads",
    ).fetchall()
    conn.close()
    assert rows == [("worker_entry", 1, "pthread", "ast_spawn", "medium")]


def test_extract_threads_taskcreate_name_literal_and_entry(tmp_path: Path) -> None:
    """A declared TASKCREATE wrapper (entry@0, name@1) yields the name string
    literal + the resolved entry rowid."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.c").write_text(
        "void pumpCycle(void) {}\n"
        "void app_start(void) {\n"
        '    SYSTEM_TASKCREATE(pumpCycle, "pumpCycle", 4096, 0, 5, &h);\n'
        "}\n",
    )
    db = _make_db(
        tmp_path,
        [(1, "pumpCycle", 1, 1), (2, "app_start", 2, 4)],
        call_edges=[],
    )
    manifest = tmp_path / "spawns.yaml"
    manifest.write_text(
        "spawns:\n"
        "  - name: SYSTEM_TASKCREATE\n"
        "    entry_arg_index: 0\n"
        "    name_arg_index: 1\n"
        "    kind: task\n",
    )
    extract_threads(db, tmp_path, manifest)
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT name, entry_memberdef_rowid, kind FROM threads",
    ).fetchall()
    conn.close()
    assert rows == [("pumpCycle", 1, "task")]


def test_default_spawn_patterns_cover_std_thread() -> None:
    """std::thread/std::jthread are C++ language primitives → shipped defaults,
    entry at arg 0, no name literal."""
    by_name = {p.name: p for p in DEFAULT_SPAWN_PATTERNS}
    for name in ("std::thread", "std::jthread"):
        assert name in by_name, f"{name} missing from defaults"
        assert by_name[name].entry_arg_index == 0
        assert by_name[name].name_arg_index is None


def test_extract_threads_std_thread_free_function(tmp_path: Path) -> None:
    """std::thread(entry, arg) with a free-function entry: the qualified callee
    (`std::thread`) matches and the entry resolves at arg 0."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.cpp").write_text(
        "void worker_fn(int a) { (void)a; }\n"
        "void boot() {\n"
        "    auto t = std::thread(worker_fn, 0);\n"
        "    (void)t;\n"
        "}\n",
    )
    db = _make_db(
        tmp_path,
        [(1, "worker_fn", 1, 1), (2, "boot", 2, 5)],
        rel_path="src/foo.cpp",
        call_edges=[],
    )
    extract_threads(db, tmp_path, None)
    conn = sqlite3.connect(str(db))
    rows = conn.execute("SELECT name, entry_memberdef_rowid, kind FROM threads").fetchall()
    conn.close()
    assert rows == [("worker_fn", 1, "pthread")]


def test_extract_threads_records_the_spawn_site_from_the_real_harvest(tmp_path: Path) -> None:
    """gh#346's PIPELINE HALF, and the reason it needs its own test at this tier: every query-side
    test of the split builds the `threads` rows by hand, so all of them would pass with the
    harvest completely unwired. That is this repo's own recorded failure — a fixture matching the
    detector rather than the world.

    THE PATH ROWID IS THE PART THAT COULD SILENTLY GO MISSING. `run_harvest` always yielded it
    and `_harvest_all_spawn_sites` always discarded it, so the spawning file was computed on every
    build and thrown away. The per-file AST walk CANNOT supply it — it is handed only a tree and
    its bytes — so if the flattener stops passing it through, the line still lands and the file
    goes NULL. Both are asserted.

    The line is the SPAWN CALL's, not the entry function's: `worker_fn` is defined on line 1 and
    spawned on line 3, so a test asserting only "some line" would not tell the two apart."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.cpp").write_text(
        "void worker_fn(int a) { (void)a; }\n"
        "void boot() {\n"
        "    auto t = std::thread(worker_fn, 0);\n"
        "    (void)t;\n"
        "}\n",
    )
    db = _make_db(
        tmp_path,
        [(1, "worker_fn", 1, 1), (2, "boot", 2, 5)],
        rel_path="src/foo.cpp",
        call_edges=[],
    )
    extract_threads(db, tmp_path, None)
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT t.name, t.spawn_line, p.name FROM threads t "
        "LEFT JOIN path p ON p.rowid = t.spawn_path_rowid"
    ).fetchall()
    conn.close()

    assert rows == [("worker_fn", 3, "src/foo.cpp")], (
        "the spawn CALL is on line 3; worker_fn is DEFINED on line 1, and recording the "
        "definition's line would answer where the thread runs rather than where it is created"
    )


def test_extract_threads_std_thread_single_call_lambda(tmp_path: Path) -> None:
    """std::thread([this]{ poll_loop(); }) — the ubiquitous modern-C++ idiom.
    A lambda body with EXACTLY ONE call resolves to that callee as the entry."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.cpp").write_text(
        "void poll_loop() {}\n"
        "void start() {\n"
        "    poll_thread_ = std::thread([this] { poll_loop(); });\n"
        "}\n",
    )
    db = _make_db(
        tmp_path,
        [(1, "poll_loop", 1, 1), (2, "start", 2, 4)],
        rel_path="src/foo.cpp",
        call_edges=[],
    )
    extract_threads(db, tmp_path, None)
    conn = sqlite3.connect(str(db))
    rows = conn.execute("SELECT name, entry_memberdef_rowid, kind FROM threads").fetchall()
    conn.close()
    assert rows == [("poll_loop", 1, "pthread")]


def test_extract_threads_std_thread_multicall_lambda_fail_closed(tmp_path: Path) -> None:
    """A lambda body with MORE THAN ONE call is ambiguous (which is the loop?)
    and must fail closed — no thread attributed to an arbitrary helper."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.cpp").write_text(
        "void setup() {}\n"
        "void serve() {}\n"
        "void start() {\n"
        "    t_ = std::thread([this] { setup(); serve(); });\n"
        "}\n",
    )
    db = _make_db(
        tmp_path,
        [(1, "setup", 1, 1), (2, "serve", 2, 2), (3, "start", 3, 5)],
        rel_path="src/foo.cpp",
        call_edges=[],
    )
    extract_threads(db, tmp_path, None)
    conn = sqlite3.connect(str(db))
    n = conn.execute("SELECT count(*) FROM threads").fetchone()[0]
    conn.close()
    assert n == 0, "a multi-call lambda body is ambiguous and must not spawn a thread row"


def test_extract_threads_std_thread_member_pointer_qualified(tmp_path: Path) -> None:
    """std::thread(&Class::method, this): the entry is a member-function
    pointer. The thread is named by its QUALIFIED entry and the rowid resolves
    against `definition` — so two classes sharing a method name stay distinct."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.cpp").write_text(
        "struct Owner { void run(); void start(); };\n"
        "void Owner::run() {}\n"
        "void Owner::start() {\n"
        "    worker_ = std::thread(&Owner::run, this);\n"
        "}\n",
    )
    # Minimal DB WITH a `definition` column so qualified resolution can match.
    db_path = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE path (name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT, definition TEXT,
            file_id INTEGER, bodyfile_id INTEGER, bodystart INTEGER, bodyend INTEGER
        );
        CREATE TABLE call_edges (
            caller_rowid INTEGER, callee_rowid INTEGER, source TEXT, confidence TEXT
        );
        """,
    )
    conn.execute("INSERT INTO path (rowid, name) VALUES (1, 'src/foo.cpp')")
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, definition, file_id, bodyfile_id, "
        "bodystart, bodyend) VALUES (?, 'function', ?, ?, 1, 1, ?, ?)",
        [
            (1, "run", "void Owner::run", 2, 2),
            (2, "start", "void Owner::start", 3, 5),
            # A decoy `run` on another class — the qualified match must NOT pick it.
            (3, "run", "void Other::run", 6, 6),
        ],
    )
    conn.commit()
    conn.close()
    extract_threads(db_path, tmp_path, None)
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("SELECT name, entry_memberdef_rowid, kind FROM threads").fetchall()
    conn.close()
    # Named by qualified entry; entry resolves to Owner::run (rowid 1), NOT the decoy.
    assert rows == [("Owner::run", 1, "pthread")]


def test_resolve_qualified_entry_rejects_suffix_collision() -> None:
    """`Owner::run` must NOT resolve to `CoOwner::run` — a bare `%Class::method`
    LIKE matches any class whose NAME ends with `Class`, so the resolver anchors
    the match to a token boundary. Guards a silent mis-attribution of a thread's
    entry (and thus its whole membership closure) to the wrong class."""
    from clew.threads import _resolve_qualified_entry

    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT, "
        "definition TEXT, file_id INTEGER, bodyfile_id INTEGER);",
    )
    # Only the suffix-colliding class is indexed; the real Owner::run is not.
    conn.execute(
        "INSERT INTO memberdef VALUES (1, 'function', 'run', 'void ns::CoOwner::run', 1, 1)"
    )
    conn.commit()
    assert _resolve_qualified_entry(conn, "Owner::run") is None
    # Once the real class IS indexed, it resolves — and to the exact class.
    conn.execute("INSERT INTO memberdef VALUES (2, 'function', 'run', 'void ns::Owner::run', 1, 1)")
    conn.commit()
    assert _resolve_qualified_entry(conn, "Owner::run") == 2
    conn.close()


def test_resolve_qualified_entry_rejects_param_type_collision() -> None:
    """The subtle case the boundary helper was hardened against, at the RESOLVER
    level: a different method whose definition merely mentions the qualified name
    inside a parameter TYPE (`void ns::CoOwner::run(Owner::run_t x)`) must not
    lend its rowid to `Owner::run`. The SQL prefilter DOES match it (`CoOwner::run(`
    contains `Owner::run(`), so `_qualified_at_boundary` is the only guard — this
    exercises the prefilter+boundary interaction, which the classic-collision test
    above does not. Would have resolved to rowid 1 before the both-sided fix.
    """
    from clew.threads import _resolve_qualified_entry

    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT, "
        "definition TEXT, file_id INTEGER, bodyfile_id INTEGER);",
    )
    conn.execute(
        "INSERT INTO memberdef VALUES "
        "(1, 'function', 'run', 'void ns::CoOwner::run(Owner::run_t x)', 1, 1)"
    )
    conn.commit()
    assert _resolve_qualified_entry(conn, "Owner::run") is None
    conn.close()


def test_extract_threads_always_creates_empty_tables(tmp_path: Path) -> None:
    """No spawn sites → threads/thread_membership still exist (empty)."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.c").write_text("void plain(void) {}\n")
    db = _make_db(tmp_path, [(1, "plain", 1, 1)], call_edges=[])
    extract_threads(db, tmp_path, None)
    conn = sqlite3.connect(str(db))
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'",
        ).fetchall()
    }
    thread_count = conn.execute("SELECT COUNT(*) FROM threads").fetchone()[0]
    conn.close()
    assert {"threads", "thread_membership"} <= tables
    assert thread_count == 0


# ─── threads: membership closure ─────────────────────────────────────────────


def test_thread_membership_is_call_closure(tmp_path: Path) -> None:
    """Membership = forward BFS over non-fuzzy call_edges from the entry.
    Graph: worker_entry -> step_a -> step_b; unrelated() is NOT reachable."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.c").write_text(
        "void step_b(void) {}\n"
        "void step_a(void) { step_b(); }\n"
        "void worker_entry(void *a) { (void)a; step_a(); }\n"
        "void unrelated(void) {}\n"
        "void boot(void) { pthread_create(&t, 0, worker_entry, 0); }\n",
    )
    db = _make_db(
        tmp_path,
        [
            (1, "step_b", 1, 1),
            (2, "step_a", 2, 2),
            (3, "worker_entry", 3, 3),
            (4, "unrelated", 4, 4),
            (5, "boot", 5, 5),
        ],
        # worker_entry(3) -> step_a(2) -> step_b(1)
        call_edges=[(3, 2), (2, 1)],
    )
    extract_threads(db, tmp_path, None)
    conn = sqlite3.connect(str(db))
    thread_id = conn.execute("SELECT id FROM threads").fetchone()[0]
    members = {
        r[0]
        for r in conn.execute(
            "SELECT memberdef_rowid FROM thread_membership WHERE thread_id = ?",
            (thread_id,),
        ).fetchall()
    }
    sources = {r[0] for r in conn.execute("SELECT DISTINCT source FROM thread_membership")}
    conn.close()
    # Entry + everything reachable; unrelated(4) and boot(5) excluded.
    assert members == {1, 2, 3}
    assert sources == {"call_closure"}


# ─── external_boundaries: the terminus ───────────────────────────────────────


def test_external_boundary_records_forwarded_dead_end(tmp_path: Path) -> None:
    """`my_cb = eventCb;` inside register_cb(param eventCb); the only in-repo
    caller forwards its OWN param out of repo → the callback dead-ends
    externally and my_cb is invoked in-repo → a terminus row (with the
    registering fn + param index), NOT a dropped edge."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.c").write_text(
        "static Cb_t my_cb = 0;\n"
        "void register_cb(int x, Cb_t eventCb) {\n"
        "    (void)x;\n"
        "    my_cb = eventCb;\n"
        "}\n"
        "void invoke_cb(int e) {\n"
        "    my_cb(e);\n"
        "}\n"
        "void app_layer(Cb_t appCb) {\n"
        "    register_cb(0, appCb);\n"
        "}\n",
    )
    # No in-repo caller ever supplies a concrete fn to app_layer(appCb) →
    # forwarding chain bottoms out externally.
    db = _make_db(
        tmp_path,
        [
            (1, "register_cb", 2, 5),
            (2, "invoke_cb", 6, 8),
            (3, "app_layer", 9, 11),
        ],
        call_edges=[],
    )
    import_callback_registration_edges(db, tmp_path)
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT memberdef_rowid, global_name, kind, registered_by_rowid, "
        "registered_param_index, confidence FROM external_boundaries",
    ).fetchall()
    conn.close()
    # invoke_cb(2) invokes my_cb; registered by register_cb(1) at param index 1.
    assert rows == [(2, "my_cb", "unresolved_callback", 1, 1, "high")]


def test_external_boundary_skips_null_only_registration(tmp_path: Path) -> None:
    """A registration whose only call site passes NULL (no forwarded param)
    must NOT be recorded as a terminus."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.c").write_text(
        "static Cb_t my_cb = 0;\n"
        "void register_cb(Cb_t eventCb) {\n"
        "    my_cb = eventCb;\n"
        "}\n"
        "void invoke_cb(int e) { my_cb(e); }\n"
        "void boot(void) { register_cb(0); }\n",
    )
    db = _make_db(
        tmp_path,
        [
            (1, "register_cb", 2, 4),
            (2, "invoke_cb", 5, 5),
            (3, "boot", 6, 6),
        ],
        call_edges=[],
    )
    import_callback_registration_edges(db, tmp_path)
    conn = sqlite3.connect(str(db))
    count = conn.execute("SELECT COUNT(*) FROM external_boundaries").fetchone()[0]
    conn.close()
    assert count == 0


def test_external_boundaries_table_always_created(tmp_path: Path) -> None:
    """Even with no registrations at all, the terminus table exists (empty)."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.c").write_text("void plain(void) {}\n")
    db = _make_db(tmp_path, [(1, "plain", 1, 1)], call_edges=[])
    import_callback_registration_edges(db, tmp_path)
    conn = sqlite3.connect(str(db))
    has = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='external_boundaries'",
    ).fetchone()
    conn.close()
    assert has is not None


# ─── dispatch_mode (inferred) ────────────────────────────────────────────────


def test_inferred_dispatch_mode_from_writer_pattern(tmp_path: Path) -> None:
    """A writer pattern declaring dispatch_mode='queued' stamps it on the
    inferred edge; the reader pattern's mode is irrelevant."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.c").write_text(
        "void producer(void) { QUEUESEND(&q, m); }\n"
        "void consumer(void) { QUEUERECEIVE(&q, &m); }\n",
    )
    db = _make_db(tmp_path, [(1, "producer", 1, 1), (2, "consumer", 2, 2)])
    patterns = tmp_path / "patterns.yaml"
    patterns.write_text(
        "writers:\n"
        "  - pattern: QUEUESEND\n"
        "    key_arg_index: 0\n"
        "    dispatch_mode: queued\n"
        "readers:\n"
        "  - pattern: QUEUERECEIVE\n"
        "    key_arg_index: 0\n",
    )
    import_shared_key_edges_inferred(db, tmp_path, patterns)
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT writer_rowid, reader_rowid, key_name, dispatch_mode, "
        "edge_triggered FROM shared_key_edges",
    ).fetchall()
    conn.close()
    # dispatch_mode='queued' from provenance; edge_triggered stays NULL.
    assert rows == [(1, 2, "q", "queued", None)]


def test_inferred_invalid_dispatch_mode_fails_closed(tmp_path: Path) -> None:
    """An invalid declared dispatch_mode REFUSES the build with a DeclarationError
    naming the file, the token and the allowed set.

    This replaces the old normalize-to-'unknown' behaviour. dispatch_mode is the
    synchrony axis a consumer reasons about: relabelling the typo 'sync' as
    'unknown' produces a database that asserts "we could not determine how this
    hand-off happens", which is indistinguishable from a genuinely undetermined
    edge and survives the build with returncode 0. The declared value comes from
    the owner's own manifest, so a load-time refusal naming the file is both the
    loudest and the most fixable signal.
    """
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.c").write_text(
        "void producer(void) { QUEUESEND(&q, m); }\n"
        "void consumer(void) { QUEUERECEIVE(&q, &m); }\n",
    )
    db = _make_db(tmp_path, [(1, "producer", 1, 1), (2, "consumer", 2, 2)])
    patterns = tmp_path / "patterns.yaml"
    patterns.write_text(
        "writers:\n"
        "  - pattern: QUEUESEND\n"
        "    key_arg_index: 0\n"
        "    dispatch_mode: sync\n"  # INVALID — not in the CHECK set
        "readers:\n"
        "  - pattern: QUEUERECEIVE\n"
        "    key_arg_index: 0\n",
    )
    with pytest.raises(DeclarationError) as exc:
        import_shared_key_edges_inferred(db, tmp_path, patterns)
    message = str(exc.value)
    assert "patterns.yaml" in message
    assert "'sync'" in message
    assert "inline, queued, keyed, unknown" in message


def test_declared_manifest_invalid_dispatch_mode_fails_closed(tmp_path: Path) -> None:
    """The data-model MANIFEST path fails closed IDENTICALLY to the accessor path.

    Before, only the accessor path validated: `_declared_keys_from_doc` read
    dispatch_mode raw and carried it to the INSERT, where the same typo surfaced
    as a bare IntegrityError with no mention of the manifest, key or token. Two
    entry points, two behaviours, for one config mistake — and via `.clew.yaml`
    `data_model:` this one is reachable through the MCP server with no CLI flag.
    """
    db = _make_db(tmp_path, [(1, "w", 1, 1), (2, "r", 2, 2)])
    manifest = tmp_path / "model.yaml"
    manifest.write_text(
        "keys:\n"
        "  - name: K\n"
        "    dispatch_mode: asynchronous\n"  # INVALID
        "    writers: [w]\n"
        "    readers: [r]\n",
    )
    with pytest.raises(DeclarationError) as exc:
        import_shared_key_edges_declared(db, manifest)
    message = str(exc.value)
    assert "model.yaml" in message
    assert "'asynchronous'" in message
    assert "inline, queued, keyed, unknown" in message


def test_inferred_dispatch_mode_defaults_unknown(tmp_path: Path) -> None:
    """A writer pattern with no dispatch_mode defaults to 'unknown'."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.c").write_text(
        'void w(void) { set("K"); }\nvoid r(void) { get("K"); }\n',
    )
    db = _make_db(tmp_path, [(1, "w", 1, 1), (2, "r", 2, 2)])
    patterns = tmp_path / "patterns.yaml"
    patterns.write_text(
        "writers:\n"
        "  - pattern: set\n"
        "    key_arg_index: 0\n"
        "readers:\n"
        "  - pattern: get\n"
        "    key_arg_index: 0\n",
    )
    import_shared_key_edges_inferred(db, tmp_path, patterns)
    conn = sqlite3.connect(str(db))
    mode = conn.execute("SELECT dispatch_mode FROM shared_key_edges").fetchone()[0]
    conn.close()
    assert mode == "unknown"


# ─── edge_triggered (declared) ───────────────────────────────────────────────


def test_declared_edge_triggered_null_without_manifest_field(tmp_path: Path) -> None:
    """A declared key that omits edge_triggered leaves the column NULL."""
    db = _make_db(tmp_path, [(1, "w", 1, 1), (2, "r", 2, 2)])
    manifest = tmp_path / "dm.toml"
    manifest.write_text(
        '[[keys]]\nname = "K"\nevent = true\nwriters = ["w"]\nreaders = ["r"]\n',
    )
    import_shared_key_edges_declared(db, manifest)
    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT dispatch_mode, edge_triggered FROM shared_key_edges",
    ).fetchone()
    conn.close()
    assert row == ("unknown", None)


def test_declared_edge_triggered_and_dispatch_mode_set(tmp_path: Path) -> None:
    """A declared key can assert dispatch_mode + edge_triggered."""
    db = _make_db(tmp_path, [(1, "w", 1, 1), (2, "r", 2, 2)])
    manifest = tmp_path / "dm.toml"
    manifest.write_text(
        '[[keys]]\nname = "K"\nevent = true\n'
        'dispatch_mode = "inline"\nedge_triggered = true\n'
        'writers = ["w"]\nreaders = ["r"]\n',
    )
    import_shared_key_edges_declared(db, manifest)
    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT dispatch_mode, edge_triggered FROM shared_key_edges",
    ).fetchone()
    conn.close()
    assert row == ("inline", 1)


# ─── keyed dispatch (MQTT) ───────────────────────────────────────────────────


## @req REQ-DDB-SCHEMA-004
def test_mqtt_dispatch_topic_literal_keyed_edge(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.c").write_text(
        "void topic_handler(void) {}\n"
        "void wire_up(void) {\n"
        '    MqttSubscribe(ctx, "cmd/req", topic_handler);\n'
        "}\n",
    )
    db = _make_db(
        tmp_path,
        [(1, "topic_handler", 1, 1), (2, "wire_up", 2, 4)],
    )
    manifest = tmp_path / "mqtt.yaml"
    manifest.write_text(
        "subscribe_functions:\n"
        "  - fn_name: MqttSubscribe\n"
        "    topic_arg_index: 1\n"
        "    handler_arg_index: 2\n",
    )
    import_mqtt_dispatch_edges(db, tmp_path, manifest)
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT writer_rowid, reader_rowid, key_name, edge_kind, dispatch_mode, "
        "declared, source FROM shared_key_edges",
    ).fetchall()
    conn.close()
    # writer = registrar wire_up(2); reader = handler(1); key = topic literal.
    assert rows == [
        (2, 1, "cmd/req", "event", "keyed", 1, "shared_key_declared"),
    ]


## @req REQ-DDB-SCHEMA-004
## @req REQ-DDB-CONFIG-001
def test_mqtt_dispatch_accepts_an_inline_document_not_only_a_path(tmp_path: Path) -> None:
    """A LIVE DEFECT, not only groundwork for gh#360's inline statement form.
    `cli._declared_or_flag` has always handed the `.clew.yaml` `mqtt_dispatch:`
    SECTION down as a parsed mapping — every sibling loader takes `Path | dict` for exactly
    that reason — while `_load_subscribe_patterns` called `.read_text` on it. So a repository
    declaring that section in its own tree crashed its own build with an `AttributeError`,
    and the suite could not see it because the one test above covers only the flag route.

    Asserted against the SAME expected row as the path test, so the two routes are pinned to
    one another rather than each to its own idea of correct.
    """
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.c").write_text(
        "void topic_handler(void) {}\n"
        "void wire_up(void) {\n"
        '    MqttSubscribe(ctx, "cmd/req", topic_handler);\n'
        "}\n",
    )
    db = _make_db(tmp_path, [(1, "topic_handler", 1, 1), (2, "wire_up", 2, 4)])

    import_mqtt_dispatch_edges(
        db,
        tmp_path,
        {
            "subscribe_functions": [
                {"fn_name": "MqttSubscribe", "topic_arg_index": 1, "handler_arg_index": 2}
            ]
        },
    )

    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT writer_rowid, reader_rowid, key_name, edge_kind, dispatch_mode, "
        "declared, source FROM shared_key_edges",
    ).fetchall()
    conn.close()
    assert rows == [(2, 1, "cmd/req", "event", "keyed", 1, "shared_key_declared")]


# ─── thread-boundary annotation ──────────────────────────────────────────────


def test_boundary_flags_logic() -> None:
    # Insufficient data → NULL/NULL.
    assert _boundary_flags(set(), {1}) == (None, None)
    assert _boundary_flags({1}, set()) == (None, None)
    # Shared thread → not crossing; reader unambiguous → to_thread set.
    assert _boundary_flags({1}, {1}) == (0, 1)
    # Disjoint → crosses; reader unambiguous.
    assert _boundary_flags({1}, {2}) == (1, 2)
    # Reader ambiguous → crosses, to_thread NULL.
    assert _boundary_flags({1}, {2, 3}) == (1, None)


def test_annotate_thread_boundaries_marks_queue_hop_crossing(tmp_path: Path) -> None:
    """producer_task spawns thread A (entry producer_entry), consumer_task
    spawns thread B (entry consumer_entry). A queue hop producer_entry ->
    consumer_entry crosses the boundary."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.c").write_text(
        "void producer_entry(void) { QUEUESEND(&q, m); }\n"
        "void consumer_entry(void) { QUEUERECEIVE(&q, &m); }\n"
        "void boot(void) {\n"
        "    pthread_create(&t1, 0, producer_entry, 0);\n"
        "    pthread_create(&t2, 0, consumer_entry, 0);\n"
        "}\n",
    )
    db = _make_db(
        tmp_path,
        [
            (1, "producer_entry", 1, 1),
            (2, "consumer_entry", 2, 2),
            (3, "boot", 3, 6),
        ],
        # no inter-entry call edges — each entry is its own closure
        call_edges=[],
    )
    # Build shared_key_edges: producer_entry -> consumer_entry over key q.
    patterns = tmp_path / "patterns.yaml"
    patterns.write_text(
        "writers:\n"
        "  - pattern: QUEUESEND\n"
        "    key_arg_index: 0\n"
        "    dispatch_mode: queued\n"
        "readers:\n"
        "  - pattern: QUEUERECEIVE\n"
        "    key_arg_index: 0\n",
    )
    import_shared_key_edges_inferred(db, tmp_path, patterns)
    extract_threads(db, tmp_path, None)
    annotate_thread_boundaries(db)

    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT writer_rowid, reader_rowid, dispatch_mode, crosses_thread, "
        "to_thread_id FROM shared_key_edges",
    ).fetchone()
    thread_for_consumer = conn.execute(
        "SELECT id FROM threads WHERE entry_memberdef_rowid = 2",
    ).fetchone()[0]
    conn.close()
    writer, reader, mode, crosses, to_thread = row
    assert (writer, reader, mode) == (1, 2, "queued")
    assert crosses == 1
    # reader (consumer_entry) is unambiguously in its own thread.
    assert to_thread == thread_for_consumer
