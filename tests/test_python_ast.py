# SPDX-License-Identifier: MIT
"""Python AST edge-layer tests (task #58): call edges, spawns, reachability seeds.

Unit-level like the rest of the suite: the committed fixture under
`tests/data/pysample/` is parsed by tree-sitter against hand-built
doxygen-shaped DBs, with no doxygen rebuild.

The memberdef rows are DERIVED from the fixture's own AST rather than written
with literal line numbers, so editing the fixture cannot silently invalidate a
test by shifting a body range. `definition` is populated in doxygen's real
Python shape — a fully dotted path, verified against a live self-index
(`clew.threads._SpawnHarvester.harvest`) — because that string is what
class-qualified entry resolution matches against.

@brief Python R1 layer tests (call edges / threads / reachability seeds).
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.call_edges import _ast_harvest_calls, import_ast_call_edges
from clew.harvest import (
    _ast_parse_one_file,
    _ts_language_for,
    try_import_tree_sitter,
)
from clew.py_entrypoints import (
    console_script_targets,
    harvest_main_guard_calls,
    python_entry_seeds,
)
from clew.pyast import (
    collect_bindings,
    dotted_name,
    is_python_tree,
    keyword_argument,
    positional_argument,
    string_value,
)
from clew.reachability import mark_reachability
from clew.shared_key_edges import (
    _SharedKeyPatterns,
    _walk_shared_key_calls,
    resolve_shared_key_patterns,
)
from clew.threads import (
    DEFAULT_PY_SPAWN_PATTERNS,
    _walk_spawn_sites,
    extract_threads,
    load_thread_patterns,
)

REPO = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO / "tests" / "data"
FIXTURE_REL = "pysample/spawner.py"
## The real C source the suite parses for the C-path regression pin. `sample/` (the
## demobot dummy project) was deleted; this tree replaced it and is REAL C — same
## role, one fewer project to maintain.
CSAMPLE_ROOT = REPO / "tests" / "data" / "csample"


## @brief Parse one source file with the pipeline's own parser.
## @param root Root the path is relative to.
## @param rel_path Repo-relative path to parse.
## @return (tree, src_bytes).
## @version 1
def _parse(root: Path, rel_path: str):
    """@brief Parse a file through the production parser plumbing.

    @return (tree, src_bytes).
    @version 1
    """
    classes = try_import_tree_sitter()
    assert classes is not None, "tree_sitter must be installed for this suite"
    language_cls, parser_cls = classes
    parsed = _ast_parse_one_file(rel_path, root / rel_path, {}, parser_cls, language_cls)
    assert parsed is not None, f"{rel_path} did not parse"
    return parsed


## @brief Enumerate a Python file's functions as (qualified, name, start, end).
## @param tree The parsed tree.
## @param src_bytes The file's raw bytes.
## @return One tuple per `def`, qualified with its enclosing class when it has one.
## @version 1
def _fixture_functions(tree, src_bytes) -> list[tuple[str, str, int, int]]:
    """Derives body ranges from the AST so the tests never carry literal line
    numbers, which would rot the moment the fixture gained a line.

    @brief Enumerate a fixture's functions and their body ranges.
    @return (qualified name, bare name, bodystart, bodyend) per function.
    @version 1
    """
    from clew.pyast import (
        class_ranges,
        enclosing_class,
        node_text,
    )

    classes = class_ranges(tree, src_bytes)
    out: list[tuple[str, str, int, int]] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type != "function_definition":
            continue
        name_node = node.child_by_field_name("name")
        if name_node is None:
            continue
        name = node_text(name_node, src_bytes)
        owner = enclosing_class(classes, node.start_byte)
        qualified = f"{owner}.{name}" if owner else name
        out.append((qualified, name, node.start_point[0] + 1, node.end_point[0] + 1))
    return out


## @brief Build a doxygen-shaped DB for the committed Python fixture.
## @param tmp_path Test temp dir for the database file.
## @param module Dotted module path used to build each `definition` string.
## @param with_call_edges Whether to create an empty `call_edges` table.
## @param root Root the indexed path is relative to; defaults to the fixture tree.
## @param rel Repo-relative path to index; defaults to the committed fixture.
## @return Path to the created database.
## @version 2
def _make_py_db(
    tmp_path: Path,
    module: str = "pysample.spawner",
    with_call_edges: bool = True,
    root: Path | None = None,
    rel: str | None = None,
):
    """`root`/`rel` default to the committed fixture, so every existing caller is
    unchanged; a test that needs a one-off source shape passes its own.

    @brief Seed memberdef/path rows mirroring a doxygen Python index.
    @return Path to the database.
    @version 2
    """
    root = root if root is not None else FIXTURE_ROOT
    rel = rel if rel is not None else FIXTURE_REL
    tree, src = _parse(root, rel)
    functions = _fixture_functions(tree, src)
    db_path = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE path (name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY,
            kind TEXT, name TEXT, definition TEXT, file_id INTEGER,
            bodyfile_id INTEGER, bodystart INTEGER, bodyend INTEGER
        );
        """,
    )
    conn.execute("INSERT INTO path (rowid, name) VALUES (1, ?)", (rel,))
    conn.executemany(
        "INSERT INTO memberdef (kind, name, definition, file_id, bodyfile_id, "
        "bodystart, bodyend) VALUES ('function', ?, ?, 1, 1, ?, ?)",
        [(name, f"None {module}.{qual}", start, end) for qual, name, start, end in functions],
    )
    if with_call_edges:
        conn.execute(
            "CREATE TABLE call_edges (caller_rowid INTEGER, callee_rowid INTEGER, "
            "source TEXT, confidence TEXT, UNIQUE(caller_rowid, callee_rowid, source))"
        )
    conn.commit()
    conn.close()
    return db_path


## @brief Read the threads table as (name, entry name, kind) rows.
## @param db_path Database to read.
## @return One tuple per thread, ordered by name.
## @version 1
def _threads(db_path: Path) -> list[tuple[str, str | None, str]]:
    """@brief Load the thread roster with each entry's resolved name.

    @return (thread name, entry function name, kind) rows.
    @version 1
    """
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT t.name, m.name, t.kind FROM threads t "
        "LEFT JOIN memberdef m ON m.rowid = t.entry_memberdef_rowid ORDER BY t.name",
    ).fetchall()
    conn.close()
    return rows


# ─── grammar routing ────────────────────────────────────────────────────────


def test_ts_language_for_routes_python() -> None:
    """Python now routes to a grammar. This REPLACES the previous assertion that
    `.py` returned None: that was a statement of the C/C++-only limitation task
    #58 exists to remove, not a behaviour to preserve. C/C++ routing is asserted
    alongside it so the addition is visibly additive. `.rs` now routes too
    (Rust support) — see tests/test_rust_ast.py for its own routing/dialect
    tests, pinned separately the way Python's are."""
    assert _ts_language_for("dir/file.py") is not None
    assert _ts_language_for("dir/stub.pyi") is not None
    assert _ts_language_for("dir/file.c") is not None
    assert _ts_language_for("dir/file.cpp") is not None
    assert _ts_language_for("dir/file.rs") is not None
    assert _ts_language_for("foo.txt") is None


def test_is_python_tree_discriminates_by_root_type() -> None:
    """Dialect selection reads the grammar's own root node type, so it must be
    true for a Python parse and false for a C one."""
    py_tree, _ = _parse(FIXTURE_ROOT, FIXTURE_REL)
    c_tree, _ = _parse(CSAMPLE_ROOT, "src/main.c")
    assert is_python_tree(py_tree) is True
    assert is_python_tree(c_tree) is False


# ─── C/C++ REGRESSION PIN ───────────────────────────────────────────────────


def test_c_harvest_output_unchanged_on_the_c_fixture() -> None:
    """THE GUARD against the Python work leaking into the C path.

    RE-BASELINED when `sample/` was deleted, and that is worth being explicit
    about. The original pin — 26 files / 97 calls — was measured on the demobot
    tree before the Python layers landed, so it guarded that specific change. This
    one is measured on `tests/data/csample/` (real C, the tree that replaced the
    dummy project) and therefore guards DRIFT FROM NOW rather than fidelity to that
    original moment. A re-derived pin is weaker evidence than an original one and
    should not be described as if it were the same thing.

    What survives the re-baseline intact is the part that actually carries the
    claim, because it is structural rather than numeric: every call site is plain
    `ast` with ZERO `ast_member` (this is C, so there are no member-access callees
    to unwrap), and ZERO spawn sites. If the Python work had leaked into the C
    walkers, those two zeros are what would break — not the file count.
    """
    patterns = {p.name: p for p in load_thread_patterns(None)}
    files = calls = plain = member = spawns = 0
    for path in sorted(CSAMPLE_ROOT.rglob("*")):
        if path.suffix not in (".c", ".h", ".cpp"):
            continue
        rel = str(path.relative_to(CSAMPLE_ROOT))
        parsed = _ast_parse_one_file(rel, path, {}, *reversed(try_import_tree_sitter()))
        if parsed is None:
            continue
        files += 1
        sites = _ast_harvest_calls(parsed[0], parsed[1])
        calls += len(sites)
        plain += sum(1 for s in sites if s[2] == "ast")
        member += sum(1 for s in sites if s[2] == "ast_member")
        spawns += len(_walk_spawn_sites(parsed[0], parsed[1], patterns))
    assert (files, calls, plain, member, spawns) == (21, 39, 39, 0, 0)


def test_c_spawn_defaults_still_present_and_unchanged() -> None:
    """Adding the Python primitives must not displace the C/C++ ones, and the
    merged map must keep each C pattern's argument positions."""
    by_name = {p.name: p for p in load_thread_patterns(None)}
    for name in ("pthread_create", "xTaskCreate", "osThreadNew", "std::thread", "std::jthread"):
        assert name in by_name, f"{name} lost from defaults"
    assert by_name["pthread_create"].entry_arg_index == 2
    assert by_name["xTaskCreate"].name_arg_index == 1
    # The C primitives carry NO keyword form; only Python's do.
    assert by_name["pthread_create"].entry_kwarg is None
    assert by_name["threading.Thread"].entry_kwarg == "target"


# ─── import bindings ────────────────────────────────────────────────────────


def test_bindings_resolve_module_alias_and_from_import(tmp_path: Path) -> None:
    """All three real spellings of the same import must resolve to one dotted
    name, because that is what lets a single dotted pattern match them all."""
    src = tmp_path / "b.py"
    src.write_text(
        "import threading\n"
        "import threading as th\n"
        "from threading import Thread\n"
        "from threading import Thread as T\n"
        "from concurrent.futures import ThreadPoolExecutor\n",
    )
    tree, data = _parse(tmp_path, "b.py")
    bindings = collect_bindings(tree, data)
    assert bindings.resolve("threading.Thread") == "threading.Thread"
    assert bindings.resolve("th.Thread") == "threading.Thread"
    assert bindings.resolve("Thread") == "threading.Thread"
    assert bindings.resolve("T") == "threading.Thread"
    assert bindings.resolve("ThreadPoolExecutor") == "concurrent.futures.ThreadPoolExecutor"


def test_bindings_refuse_unbound_and_foreign_names(tmp_path: Path) -> None:
    """An unbound name resolves to None (never to itself), and a name imported
    from elsewhere resolves to THAT origin — the mechanism that refuses
    clew's own `Thread` dataclass."""
    src = tmp_path / "b.py"
    src.write_text("from .models import Thread\n")
    tree, data = _parse(tmp_path, "b.py")
    bindings = collect_bindings(tree, data)
    assert bindings.resolve("Thread") == ".models.Thread"
    assert bindings.resolve("Thread") != "threading.Thread"
    assert bindings.resolve("SomethingLocal") is None


def test_bindings_bind_receiver_only_from_resolvable_constructor(tmp_path: Path) -> None:
    """A receiver bound to a resolvable constructor gets a type; one bound to an
    attribute does not. That asymmetry is what stops `.submit(` from matching on
    any object with a `submit` method."""
    src = tmp_path / "b.py"
    src.write_text(
        "import asyncio\n"
        "from concurrent.futures import ThreadPoolExecutor\n"
        "def f(self):\n"
        "    pool = ThreadPoolExecutor()\n"
        "    loop = asyncio.get_event_loop()\n"
        "    other = self._loop\n",
    )
    tree, data = _parse(tmp_path, "b.py")
    bindings = collect_bindings(tree, data)
    assert bindings.resolve("pool.submit") == "concurrent.futures.ThreadPoolExecutor.submit"
    assert bindings.resolve("loop.run_in_executor") == "asyncio.AbstractEventLoop.run_in_executor"
    # `self._loop` is not a constructor, so `other` stays unbound — fail closed.
    assert bindings.resolve("other.run_in_executor") is None


def test_dotted_name_refuses_non_static_chain(tmp_path: Path) -> None:
    """A chain containing a call or subscript has no static name and must be
    refused rather than having its source text taken literally."""
    src = tmp_path / "b.py"
    src.write_text("a = f().b\nc = d['k'].e\ng = h.i.j\n")
    tree, data = _parse(tmp_path, "b.py")
    found = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type == "attribute":
            found.append(dotted_name(node, data))
    assert "h.i.j" in found
    assert None in found  # f().b / d['k'].e refused


# ─── argument reading ───────────────────────────────────────────────────────


def test_positional_argument_skips_keyword_arguments(tmp_path: Path) -> None:
    """`Thread(group, target, name=...)`: counting every named child (the C
    helper's rule) would let a keyword argument occupy a positional slot and
    shift every index after it."""
    src = tmp_path / "b.py"
    src.write_text("f(a, b, kw=c, other=d)\n")
    tree, data = _parse(tmp_path, "b.py")
    call = next(n for n in _walk_nodes(tree) if n.type == "call")
    assert dotted_name(positional_argument(call, 0), data) == "a"
    assert dotted_name(positional_argument(call, 1), data) == "b"
    assert positional_argument(call, 2) is None  # only two positionals exist
    assert dotted_name(keyword_argument(call, "kw"), data) == "c"
    assert keyword_argument(call, "absent") is None


def test_string_value_reads_content_not_quotes(tmp_path: Path) -> None:
    """Python strings carry their quotes in the node text and vary in style, so
    the C path's `strip('"')` would leave quotes on a single-quoted literal. An
    interpolated f-string is refused rather than recorded as a key."""
    src = tmp_path / "b.py"
    src.write_text("a = 'single'\nb = \"double\"\nc = f'x{a}y'\n")
    tree, data = _parse(tmp_path, "b.py")
    values = [string_value(n, data) for n in _walk_nodes(tree) if n.type == "string"]
    assert "single" in values
    assert "double" in values
    assert None in values  # the interpolated f-string


## @brief Every node in a tree, for compact assertions.
## @param tree A parsed tree.
## @return All nodes in walk order.
## @version 1
def _walk_nodes(tree) -> list:
    """@brief Flatten a parse tree into a node list.

    @return All nodes.
    @version 1
    """
    out = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        out.append(node)
    return out


# ─── Layer 3: Python call edges ─────────────────────────────────────────────


def test_python_call_provenance_splits_plain_and_attribute() -> None:
    """A bare-identifier callee is `ast`; an attribute-qualified one is
    `ast_member`, REUSING the C++ tags because it is the same fact — the callee
    was reduced to its unqualified tail, which may match several classes.

    The closed-world bound at the end is the point of the test: a THIRD provenance
    reaching this harvest must be a deliberate act. `binding` (gh#1) is the third,
    and it is pinned by name below so widening the bound cannot silently re-admit a
    stray tag."""
    tree, src = _parse(FIXTURE_ROOT, FIXTURE_REL)
    sites = _ast_harvest_calls(tree, src)
    by_name = {(s[0], s[2]) for s in sites}
    # `worker()` inside a lambda / `helper()` — bare identifiers.
    assert ("helper", "ast") in by_name
    assert ("worker", "ast") in by_name
    # `threading.Thread(...)` and `.start()` — attribute-qualified tails.
    assert ("Thread", "ast_member") in by_name
    assert ("start", "ast_member") in by_name
    # The fixture's `threading.Thread(target=worker)` BINDS `worker` (gh#1).
    assert ("worker", "binding") in by_name
    assert {s[2] for s in sites} <= {"ast", "ast_member", "binding"}


def test_python_self_qualified_call_is_member_provenance() -> None:
    """`self.method()` is the Python analogue of C++'s `obj.method()`; its tail
    is what `memberdef.name` stores, so it must be recorded as `ast_member`."""
    tree, src = _parse(FIXTURE_ROOT, FIXTURE_REL)
    sites = _ast_harvest_calls(tree, src)
    starts = [s for s in sites if s[0] == "start"]
    assert starts, "expected `.start()` call sites in the fixture"
    assert all(s[2] == "ast_member" for s in starts)


def test_python_call_edges_land_in_db(tmp_path: Path) -> None:
    """End-to-end: the Python harvest must actually produce `call_edges` rows,
    the layer that measured exactly ZERO before this change."""
    db = _make_py_db(tmp_path)
    import_ast_call_edges(db, FIXTURE_ROOT)
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT source, COUNT(*) FROM call_edges GROUP BY source ORDER BY source",
    ).fetchall()
    conn.close()
    sources = dict(rows)
    assert sources.get("ast", 0) > 0, "no plain-identifier Python call edges"
    assert sum(sources.values()) > 0


def test_python_comprehension_and_decorator_calls_are_reached(tmp_path: Path) -> None:
    """Comprehension bodies and decorator invocations need no special case — each
    is a `call` node — but that must be verified rather than assumed."""
    src = tmp_path / "b.py"
    src.write_text(
        "def outer():\n"
        "    xs = [inner(i) for i in range(3)]\n"
        "    return xs\n"
        "@registry.register('x')\n"
        "def handler():\n"
        "    pass\n",
    )
    tree, data = _parse(tmp_path, "b.py")
    names = {s[0] for s in _ast_harvest_calls(tree, data)}
    assert "inner" in names  # comprehension body
    assert "range" in names
    assert "register" in names  # decorator call, attribute-qualified


# ─── thread spawns ──────────────────────────────────────────────────────────


def test_default_py_spawn_patterns_are_all_dotted() -> None:
    """Every shipped Python default MUST be a dotted path. A bare-tail default
    would fabricate a thread at any same-named constructor — the concrete bug
    clew's own `Thread` dataclass poses."""
    assert DEFAULT_PY_SPAWN_PATTERNS, "expected shipped Python spawn primitives"
    for pattern in DEFAULT_PY_SPAWN_PATTERNS:
        assert "." in pattern.name, f"{pattern.name} is not dotted — it could false-match"


def test_py_spawn_kinds_map_each_primitive_honestly(tmp_path: Path) -> None:
    """The kind column is what a consumer reads to decide whether two functions
    can race, so each primitive must carry its real execution context: a thread
    is 'pthread', a Process is 'process' (separate address space), a task is
    'coroutine' (same OS thread), a pool submission is 'task'."""
    db = _make_py_db(tmp_path)
    extract_threads(db, FIXTURE_ROOT, None)
    kinds = {name: kind for name, _entry, kind in _threads(db)}
    assert kinds.get("worker") == "pthread"  # Thread(target=worker) — bare import
    assert "process" in kinds.values()
    assert "coroutine" in kinds.values()
    assert "task" in kinds.values()


def test_py_thread_keyword_target_resolves_entry_rowid(tmp_path: Path) -> None:
    """`target=` is a KEYWORD argument in essentially all real Python (all 40
    measured sites), so the keyword path — not the positional index — is what
    must resolve the entry to a rowid."""
    db = _make_py_db(tmp_path)
    extract_threads(db, FIXTURE_ROOT, None)
    entries = {name: entry for name, entry, _kind in _threads(db)}
    assert entries.get("worker") == "worker", "keyword target= did not resolve"


def test_py_thread_name_literal_wins_over_qualified_entry(tmp_path: Path) -> None:
    """`name="poller"` is the author's own label and must become the thread's
    name; a spawn with no literal falls back to the qualified entry."""
    db = _make_py_db(tmp_path)
    extract_threads(db, FIXTURE_ROOT, None)
    names = {name for name, _entry, _kind in _threads(db)}
    assert "poller" in names  # Poller.start passes name="poller"
    assert "Reader._run" in names  # Reader.start passes no name


def test_py_same_method_name_in_two_classes_resolves_distinctly(tmp_path: Path) -> None:
    """THE FABRICATION GUARD. `Poller._run` and `Reader._run` share a bare name,
    and both are spawned via `target=self._run`. Each thread must resolve to its
    OWN class's rowid; collapsing them onto one rowid would invent a shared entry
    point. Measured motivation: `target=self._run` occurs 5 times in 5 unrelated
    classes in `a Python codebase`."""
    db = _make_py_db(tmp_path)
    extract_threads(db, FIXTURE_ROOT, None)
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT t.name, t.entry_memberdef_rowid, m.definition FROM threads t "
        "JOIN memberdef m ON m.rowid = t.entry_memberdef_rowid WHERE m.name='_run' "
        "ORDER BY t.name",
    ).fetchall()
    conn.close()
    assert len(rows) == 2, f"expected both _run threads to resolve, got {rows}"
    rowids = {r[1] for r in rows}
    assert len(rowids) == 2, f"both _run threads collapsed onto one rowid: {rows}"
    definitions = {r[2] for r in rows}
    assert any("Poller._run" in d for d in definitions)
    assert any("Reader._run" in d for d in definitions)


def test_py_same_entry_through_two_primitives_stays_two_threads(tmp_path: Path) -> None:
    """A function spawned as BOTH a thread and a process is TWO execution
    contexts, and `kind` is the column a consumer reads to decide whether they
    can share memory. The `threads` UNIQUE key used to be (name,
    entry_memberdef_rowid) with no `kind`, so the two rows collapsed and the
    survivor's kind was whichever tree-sitter's DFS popped first — a wrong
    answer, not a missing one. Both must survive with their own kinds."""
    (tmp_path / "dual.py").write_text(
        "import multiprocessing\n"
        "import threading\n"
        "def body():\n"
        "    pass\n"
        "def boot():\n"
        "    threading.Thread(target=body).start()\n"
        "    multiprocessing.Process(target=body).start()\n",
    )
    db = _make_py_db(tmp_path, module="dual", root=tmp_path, rel="dual.py")
    extract_threads(db, tmp_path, None)
    rows = [(name, kind) for name, _entry, kind in _threads(db) if name == "body"]
    assert sorted(kind for _n, kind in rows) == ["process", "pthread"]


def test_py_lookalike_constructor_is_refused(tmp_path: Path) -> None:
    """`Decoy(target=noop)` is shaped exactly like a spawn but imported from
    `.models`. Resolving the callee through the file's own imports must refuse
    it. This is the committed regression for clew's own `Thread` dataclass."""
    db = _make_py_db(tmp_path)
    extract_threads(db, FIXTURE_ROOT, None)
    names = {name for name, _entry, _kind in _threads(db)}
    assert "noop" not in names, "a look-alike constructor fabricated a thread"
    assert not any("Decoy" in n for n in names)


def test_py_single_call_lambda_entry_resolves(tmp_path: Path) -> None:
    """`target=lambda: helper()` — a lambda body with exactly one call resolves
    to that callee, matching the C++ layer's rule."""
    db = _make_py_db(tmp_path)
    extract_threads(db, FIXTURE_ROOT, None)
    entries = {name: entry for name, entry, _kind in _threads(db)}
    assert entries.get("helper") == "helper"


def test_py_multicall_lambda_entry_fails_closed(tmp_path: Path) -> None:
    """A lambda body with MORE THAN ONE call is ambiguous, so no thread may be
    recorded — never one attributed to an arbitrary leading helper."""
    tree, src = _parse(FIXTURE_ROOT, FIXTURE_REL)
    patterns = {p.name: p for p in load_thread_patterns(None)}
    sites = _walk_spawn_sites(tree, src, patterns)
    # `spawn_multi_lambda` uses (noop(), helper()); `noop` must never be an entry.
    entries = {site[1] for site in sites}
    assert "noop" not in entries, "a multi-call lambda produced a thread entry"


def test_py_declared_local_wrapper_matches_by_raw_name(tmp_path: Path) -> None:
    """A module-local spawn wrapper has no import binding, so it falls through to
    raw-text matching and a declared `--thread-patterns` entry still works. No
    built-in default can reach that path, since every default is dotted."""
    src = tmp_path / "w.py"
    src.write_text("def entry():\n    pass\ndef boot():\n    spawn_task(entry, 'w')\n")
    tree, data = _parse(tmp_path, "w.py")
    manifest = tmp_path / "spawns.yaml"
    manifest.write_text(
        "spawns:\n  - name: spawn_task\n    entry_arg_index: 0\n    name_arg_index: 1\n",
    )
    patterns = {p.name: p for p in load_thread_patterns(manifest)}
    sites = _walk_spawn_sites(tree, data, patterns)
    assert [s[1] for s in sites] == ["entry"]
    assert [s[0] for s in sites] == ["w"]


def test_py_thread_membership_is_populated(tmp_path: Path) -> None:
    """A resolved entry must produce a call-closure membership, so the thread
    layer is queryable and not merely present."""
    db = _make_py_db(tmp_path)
    import_ast_call_edges(db, FIXTURE_ROOT)
    extract_threads(db, FIXTURE_ROOT, None)
    conn = sqlite3.connect(str(db))
    count = conn.execute("SELECT COUNT(*) FROM thread_membership").fetchone()[0]
    conn.close()
    assert count > 0


# ─── reachability seeds ─────────────────────────────────────────────────────


def test_console_script_targets_reads_both_table_spellings(tmp_path: Path) -> None:
    """PEP 621 and poetry are both real, so both tables are read rather than one
    build backend being assumed."""
    (tmp_path / "pyproject.toml").write_text(
        '[project.scripts]\nfoo = "pkg.mod:main"\n[tool.poetry.scripts]\nbar = "pkg.other:run"\n',
    )
    targets = console_script_targets(tmp_path)
    assert set(targets) == {"pkg.mod:main", "pkg.other:run"}
    assert console_script_targets(tmp_path / "nope") == []


def test_console_script_seed_resolves_the_declared_module(tmp_path: Path) -> None:
    """clew declares two entry points that share the bare name `main`. The
    seed must resolve against the fully dotted `definition`, so a declared
    `pkg.cli:main` seeds cli's `main` and not the other one."""
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT, definition TEXT,
            file_id INTEGER, bodyfile_id INTEGER, bodystart INTEGER, bodyend INTEGER
        );
        """,
    )
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, definition, file_id, bodyfile_id, "
        "bodystart, bodyend) VALUES (?, 'function', 'main', ?, 1, 1, 1, 2)",
        [(1, "None pkg.cli.main"), (2, "None pkg.server.main")],
    )
    conn.commit()
    conn.close()
    (tmp_path / "pyproject.toml").write_text('[project.scripts]\nx = "pkg.cli:main"\n')
    seeds = python_entry_seeds(db, tmp_path)
    assert seeds == {1}, "console script resolved to the wrong same-named function"


def test_main_guard_calls_are_harvested() -> None:
    """The guard's callee is the entry point; a call elsewhere in the file is
    not. Matching the CONDITION is what keeps this from seeding any conditional
    call."""
    tree, src = _parse(FIXTURE_ROOT, FIXTURE_REL)
    assert harvest_main_guard_calls(tree, src) == ["guarded_main"]


def test_main_guard_ignores_a_plain_if_and_a_mere_mention(tmp_path: Path) -> None:
    """A module that merely mentions the string `"__main__"`, or has an unrelated
    `if`, must contribute no seed."""
    src = tmp_path / "b.py"
    src.write_text(
        "LABEL = '__main__'\ndef f(flag):\n    if flag:\n        side_effect()\n",
    )
    tree, data = _parse(tmp_path, "b.py")
    assert harvest_main_guard_calls(tree, data) == []


def test_main_guard_seed_resolves_to_the_guarded_function(tmp_path: Path) -> None:
    """End-to-end: the fixture's `guarded_main` must be seeded."""
    db = _make_py_db(tmp_path)
    seeds = python_entry_seeds(db, FIXTURE_ROOT)
    conn = sqlite3.connect(str(db))
    names = {
        conn.execute("SELECT name FROM memberdef WHERE rowid=?", (r,)).fetchone()[0] for r in seeds
    }
    conn.close()
    assert "guarded_main" in names


def test_extra_seeds_rescue_a_self_loop_false_orphan(tmp_path: Path) -> None:
    """The exact shape measured on `a Python codebase`: doxygen attributes a
    `__main__` guard's call to the guarded function ITSELF, so the function has a
    non-fuzzy incoming edge (excluding it from the zero-incoming source) and its
    only caller is itself. Without a structural seed it is a FALSE orphan; with
    one it is live. `dead_helper` must stay orphan either way, proving the seed
    does not simply mark everything live."""
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT,
            file_id INTEGER, bodyfile_id INTEGER, bodystart INTEGER, bodyend INTEGER
        );
        CREATE TABLE call_edges (caller_rowid INTEGER, callee_rowid INTEGER,
            source TEXT, confidence TEXT);
        """,
    )
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, file_id, bodyfile_id, bodystart, "
        "bodyend) VALUES (?, 'function', ?, 1, 1, ?, ?)",
        [(1, "guarded", 1, 2), (2, "reached", 3, 4), (3, "dead_helper", 5, 6), (4, "dead2", 7, 8)],
    )
    conn.executemany(
        "INSERT INTO call_edges VALUES (?, ?, 'ast', 'resolved')",
        # guarded -> guarded (the doxygen self-loop), guarded -> reached,
        # and a dead mutually-recursive pair so neither is zero-incoming.
        [(1, 1), (1, 2), (3, 4), (4, 3)],
    )
    conn.commit()
    conn.close()

    mark_reachability(db, entry_patterns=["nothing_matches"])
    conn = sqlite3.connect(str(db))
    before = dict(conn.execute("SELECT memberdef_rowid, status FROM symbol_liveness"))
    conn.close()
    assert before[1] == "orphan", "expected the self-loop entry to be a false orphan"

    mark_reachability(db, entry_patterns=["nothing_matches"], extra_seeds={1})
    conn = sqlite3.connect(str(db))
    after = dict(conn.execute("SELECT memberdef_rowid, status FROM symbol_liveness"))
    conn.close()
    assert after[1] == "live", "structural seed did not rescue the entry point"
    assert after[2] == "live", "the entry's callee should now be reachable"
    assert after[3] == "orphan", "a genuinely dead function must stay orphan"
    assert after[4] == "orphan"


def test_python_entry_seeds_empty_for_a_c_repo(tmp_path: Path) -> None:
    """A C/C++ codebase has no pyproject.toml and no Python files, so the seed set
    must be empty and the C seed set bit-identical to before."""
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT, definition TEXT,
            file_id INTEGER, bodyfile_id INTEGER, bodystart INTEGER, bodyend INTEGER
        );
        """,
    )
    conn.execute("INSERT INTO path (rowid, name) VALUES (1, 'src/main.c')")
    conn.execute(
        "INSERT INTO memberdef (rowid, kind, name, definition, file_id, bodyfile_id, "
        "bodystart, bodyend) VALUES (1, 'function', 'main', 'int main()', 1, 1, 1, 3)",
    )
    conn.commit()
    conn.close()
    assert python_entry_seeds(db, CSAMPLE_ROOT) == set()


# ─── shared-key dataflow ────────────────────────────────────────────────────


def test_no_builtin_python_accessor_default_exists() -> None:
    """`publish` / `subscribe` / `get` / `set` are ordinary method names on
    countless unrelated objects, so shipping them as defaults would manufacture a
    dataflow graph out of coincidence. The built-in accessor defaults must stay
    the ingot C convention only."""
    writers, readers, _aliases = resolve_shared_key_patterns(None)
    prefixes = {getattr(p, "prefix", None) for p in (*writers, *readers)}
    assert prefixes == {"DataModel_Set_", "DataModel_Get_"}


def test_py_declared_accessors_pair_enum_keys(tmp_path: Path) -> None:
    """A DECLARED Python accessor convention must actually produce paired sites.
    The key shape is an enum member (`Topic.ALPHA`) — an `attribute`, not the bare
    identifier C uses — which is what a real repo writes (measured on
    `a Python codebase`: every keyed publish keys on `EventType.*`)."""
    src = tmp_path / "bus.py"
    src.write_text(
        "def emit_alpha(bus):\n"
        "    bus.publish(Topic.ALPHA, 1)\n"
        "def on_alpha(bus):\n"
        "    bus.subscribe(Topic.ALPHA, handler)\n"
        "def emit_computed(bus, t):\n"
        "    bus.publish(t, 2)\n",
    )
    manifest = tmp_path / "keys.yaml"
    manifest.write_text(
        "writers:\n  - pattern: publish\n    key_arg_index: 0\n"
        "readers:\n  - pattern: subscribe\n    key_arg_index: 0\n",
    )
    tree, data = _parse(tmp_path, "bus.py")
    writers, readers, aliases = resolve_shared_key_patterns(manifest)
    out = _walk_shared_key_calls(tree, data, _SharedKeyPatterns(writers, readers, aliases))
    assert [w[1] for w in out["w"]] == ["Topic.ALPHA"]
    assert [r[1] for r in out["r"]] == ["Topic.ALPHA"]
    # `publish(t, 2)` keys on a variable — computed, so fail-closed unresolved.
    assert len(out["u"]) == 1


def test_py_shared_key_walk_is_empty_without_a_declaration(tmp_path: Path) -> None:
    """With no declared convention the Python walk must produce nothing, however
    many `publish`/`subscribe` calls the file contains."""
    src = tmp_path / "bus.py"
    src.write_text("def f(bus):\n    bus.publish(Topic.ALPHA, 1)\n    bus.subscribe(cb)\n")
    tree, data = _parse(tmp_path, "bus.py")
    writers, readers, aliases = resolve_shared_key_patterns(None)
    out = _walk_shared_key_calls(tree, data, _SharedKeyPatterns(writers, readers, aliases))
    assert out == {"w": [], "r": [], "u": []}


@pytest.mark.parametrize("kind", ["process", "coroutine"])
def test_new_thread_kinds_are_registered_in_the_vocabulary(kind: str) -> None:
    """Both new kinds must be real vocabulary members, so the `threads.kind`
    CHECK accepts them and a declared manifest can validate against them."""
    from clew.vocabulary import THREAD_KIND

    assert kind in THREAD_KIND
    assert THREAD_KIND.validated(kind, owner="test", field="kind") == kind


##
# @brief A module-aliased thread ENTRY must be resolved through the same import map as the callee.
# @param tmp_path Pytest temp dir.
# @return None.
# @version 1
def test_an_aliased_thread_entry_is_resolved_through_the_import_map(tmp_path: Path) -> None:
    """#498. The CALLEE has been resolved through `PyBindings` since the Python thread layer
    landed — `bindings.resolve("th.Thread") == "threading.Thread"` is asserted just above. The
    ENTRY was not, so `threading.Thread(target=dox.func)` stored the raw source text
    `"dox.func"`, doxygen's `definition` holds the real `clew.doxygen.func`, and the qualified
    lookup could never match. The row was inserted with a NULL entry rowid.

    THAT IS A RESOLUTION FAILURE RATHER THAN FAIL-CLOSED BEHAVIOUR, by this repo's own invariant:
    `test_self_index_thread_layer_resolves_its_entries` says a NULL is correct ONLY when the
    entry's own tail is genuinely absent from the index. Here the tail is present and unique.

    THE FIX IS NOT A TAIL MATCH, deliberately. Falling back to the bare tail would resolve this
    case and silently borrow a same-named stranger's rowid the day a second `func` appears —
    the gh#347 shape, and exactly what the no-fallback rule in `_insert_threads` exists to
    prevent. Resolving the ALIAS is different in kind: the module is then KNOWN rather than
    guessed, so the qualified lookup stays exact.

    @brief An aliased entry resolves to its real dotted path.
    @return None.
    @version 1
    """
    src = tmp_path / "c.py"
    src.write_text(
        "import threading\n"
        "from clew import doxygen as dox\n"
        "import clew.testscope as ts\n"
        "\n"
        "class Holder:\n"
        "    def _run(self):\n"
        "        pass\n"
        "    def go(self):\n"
        "        threading.Thread(target=self._run).start()\n"
        "\n"
        "def spawn():\n"
        "    threading.Thread(target=dox._write_doxyfile_stdin).start()\n"
        "    threading.Thread(target=ts.is_test_path).start()\n",
        encoding="utf-8",
    )
    tree, data = _parse(tmp_path, "c.py")
    bindings = collect_bindings(tree, data)

    ## The import map already knows both aliases — this is the machinery the entry path must use.
    assert bindings.resolve("dox") == "clew.doxygen"
    assert bindings.resolve("ts") == "clew.testscope"

    sites = _walk_spawn_sites(tree, data, {p.name: p for p in load_thread_patterns(None)})
    ## A site is a flat septet; index 3 is the QUALIFIED entry, which is the field the
    ## resolver matches against doxygen's `definition`. Indexed rather than named because the
    ## walker returns plain lists for the harvest cache, not `_SpawnSite` objects.
    qualified = {row[3] for row in sites}

    assert "clew.doxygen._write_doxyfile_stdin" in qualified, (
        f"an aliased entry was stored unresolved; doxygen records the real module path, so a "
        f"raw alias can never match the qualified lookup. Got: {sorted(qualified)}"
    )
    assert "clew.testscope.is_test_path" in qualified, (
        f"`import x.y as z` form not resolved either. Got: {sorted(qualified)}"
    )
    ## AND THE self.method REWRITE MUST SURVIVE. It is the one entry form that already worked, so
    ## it is the regression most worth pinning while changing this code path.
    assert "Holder._run" in qualified, (
        f"the self.method -> Class.method rewrite regressed. Got: {sorted(qualified)}"
    )
