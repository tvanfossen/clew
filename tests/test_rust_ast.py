# SPDX-License-Identifier: MIT
"""Rust tree-sitter dialect tests — the AST/call-graph half of Rust support
(clew/rustdoc.py covers the structural half; see tests/test_rustdoc.py and
tests/test_cli_rustdoc.py).

Mirrors tests/test_python_ast.py's shape: grammar routing, then one section
per harvester that gained Rust support (call_edges, threads, locks,
critical_sections, callback_edges). Skipped wholesale when tree-sitter-rust
isn't importable, the same way the Python suite skips on a missing C/C++
grammar.

@brief Tests for the Rust tree-sitter dialect across the AST harvesters.
@version 1
"""

from __future__ import annotations


import pytest

from clew.harvest import _ts_language_for, try_import_tree_sitter

try:
    import tree_sitter_rust as _tsrust
except ImportError:
    _tsrust = None

pytestmark = pytest.mark.skipif(
    try_import_tree_sitter() is None or _tsrust is None,
    reason="Rust AST tests need tree_sitter + tree-sitter-rust",
)


def _parse(src: str):
    from tree_sitter import Language, Parser

    lang = Language(_tsrust.language())
    parser = Parser(lang)
    src_bytes = src.encode("utf-8")
    return parser.parse(src_bytes), src_bytes


# ─── grammar routing ────────────────────────────────────────────────────────


def test_ts_language_for_routes_rust():
    assert _ts_language_for("dir/file.rs") is not None
    assert _ts_language_for("foo.txt") is None


# ─── call_edges: Rust needs no dedicated branch ─────────────────────────────


def test_call_edges_resolves_direct_and_qualified_calls():
    from clew.call_edges import _ast_harvest_calls

    tree, src = _parse(
        "fn helper(x: i32) -> i32 { x + 1 }\n"
        "fn main() {\n"
        "    helper(1);\n"
        "    std::thread::spawn(|| {});\n"
        "}\n"
    )
    sites = _ast_harvest_calls(tree, src)
    names = {s[0] for s in sites}
    assert "helper" in names
    assert "spawn" in names
    spawn_site = next(s for s in sites if s[0] == "spawn")
    assert spawn_site[3] == "std::thread::spawn"


def test_call_edges_resolves_method_calls():
    from clew.call_edges import _ast_harvest_calls

    tree, src = _parse(
        "struct Foo;\nimpl Foo {\n    fn go(&self) {}\n}\nfn main() {\n    let f = Foo;\n    f.go();\n}\n"
    )
    sites = _ast_harvest_calls(tree, src)
    assert any(s[0] == "go" and s[2] == "ast_member" for s in sites)


# ─── threads: std::thread::spawn ────────────────────────────────────────────


def test_thread_spawn_resolves_closure_entry():
    from clew.threads import _walk_spawn_sites, load_thread_patterns

    tree, src = _parse(
        "fn worker() {}\nfn main() {\n    std::thread::spawn(|| { worker(); });\n}\n"
    )
    patterns = {p.name: p for p in load_thread_patterns(None)}
    sites = _walk_spawn_sites(tree, src, patterns)
    assert len(sites) == 1
    thread_name, entry_name, kind, qualified_entry, _sep, line, spawn_fn = sites[0]
    assert entry_name == "worker"
    assert kind == "pthread"
    assert spawn_fn == "main"
    assert line == 3


def test_thread_spawn_aliased_import_form():
    from clew.threads import _walk_spawn_sites, load_thread_patterns

    tree, src = _parse(
        "use std::thread;\nfn worker() {}\nfn main() {\n    thread::spawn(|| { worker(); });\n}\n"
    )
    patterns = {p.name: p for p in load_thread_patterns(None)}
    sites = _walk_spawn_sites(tree, src, patterns)
    assert len(sites) == 1
    assert sites[0][1] == "worker"


# ─── locks: Mutex/RwLock guard bindings ─────────────────────────────────────


def test_lock_site_detects_mutex_lock_binding():
    from clew.locks import _walk_lock_sites, load_lock_patterns

    tree, src = _parse(
        "struct Counter { mutex: std::sync::Mutex<i32> }\n"
        "impl Counter {\n"
        "    fn bump(&self) {\n"
        "        let mut g = self.mutex.lock().unwrap();\n"
        "        *g += 1;\n"
        "    }\n"
        "}\n"
    )
    patterns = {p.name: p for p in load_lock_patterns(None)}
    sites = _walk_lock_sites(tree, src, patterns)
    assert len(sites) == 1
    name, operand, scope, line, end_line, form, kind, mode, role, confidence, calls = sites[0]
    assert name == "lock"
    assert operand == "self.mutex"
    assert scope == "class:Counter"
    assert form == "raii"
    assert kind == "mutex"
    assert mode == "exclusive"
    assert confidence == "high"


def test_lock_site_detects_mutex_lock_with_poison_recovery():
    """`.lock().unwrap_or_else(|e| e.into_inner())` is the standard
    poison-recovery idiom (vs. plain `.unwrap()`) and must still be
    recognized as a lock acquisition — found missing against a real
    codebase (tools_sqc/src/progress.rs), where every guard used this form
    and none were detected."""
    from clew.locks import _walk_lock_sites, load_lock_patterns

    tree, src = _parse(
        "struct Counter { mutex: std::sync::Mutex<i32> }\n"
        "impl Counter {\n"
        "    fn bump(&self) {\n"
        "        let mut g = self.mutex.lock().unwrap_or_else(|e| e.into_inner());\n"
        "        *g += 1;\n"
        "    }\n"
        "}\n"
    )
    patterns = {p.name: p for p in load_lock_patterns(None)}
    sites = _walk_lock_sites(tree, src, patterns)
    assert len(sites) == 1
    name, operand, _scope, _line, _end_line, form, kind, _mode, _role, _confidence, _calls = sites[
        0
    ]
    assert name == "lock"
    assert operand == "self.mutex"
    assert form == "raii"
    assert kind == "mutex"


def test_lock_site_detects_rwlock_read_and_write():
    from clew.locks import _walk_lock_sites, load_lock_patterns

    tree, src = _parse(
        "fn f(rw: &std::sync::RwLock<i32>) {\n"
        "    let r = rw.read().unwrap();\n"
        "    let w = rw.write().unwrap();\n"
        "}\n"
    )
    patterns = {p.name: p for p in load_lock_patterns(None)}
    sites = _walk_lock_sites(tree, src, patterns)
    kinds_modes = {(s[0], s[7]) for s in sites}
    assert ("read", "shared") in kinds_modes
    assert ("write", "exclusive") in kinds_modes


# ─── critical_sections: block/jump node names generalized for Rust ─────────


def test_critical_section_excludes_call_after_early_return():
    from clew.locks import _walk_lock_sites, load_lock_patterns

    tree, src = _parse(
        "fn f(m: &std::sync::Mutex<i32>, bad: bool) {\n"
        "    let g = m.lock().unwrap();\n"
        "    if bad {\n"
        "        return;\n"
        "    }\n"
        "    do_thing();\n"
        "}\n"
    )
    patterns = {p.name: p for p in load_lock_patterns(None)}
    sites = _walk_lock_sites(tree, src, patterns)
    assert len(sites) == 1
    calls = sites[0][10]
    called_names = {c[0] for c in calls}
    assert "do_thing" in called_names


# ─── callback_edges: closure/fn-pointer field registration ──────────────────


def test_callback_edges_resolves_struct_literal_registration():
    from clew.callback_edges import _harvest_callback_file

    tree, src = _parse(
        "fn handler(x: i32) -> i32 { x }\n"
        "struct Widget { callback: fn(i32) -> i32 }\n"
        "impl Widget {\n"
        "    fn new(h: fn(i32) -> i32) -> Self {\n"
        "        Self { callback: h }\n"
        "    }\n"
        "    fn fire(&self, x: i32) -> i32 {\n"
        "        (self.callback)(x)\n"
        "    }\n"
        "}\n"
        "fn build() -> Widget {\n"
        "    Widget::new(handler)\n"
        "}\n"
    )
    out = _harvest_callback_file(tree, src)
    reg_globals = {r[1] for r in out["regs"]}
    assert "Widget::callback" in reg_globals
    call_names = {c[1] for c in out["calls"]}
    assert "new" in call_names
    assert "Widget::callback" in call_names


def test_callback_edges_resolves_assignment_registration():
    from clew.callback_edges import _harvest_callback_file

    tree, src = _parse(
        "struct Widget { callback: fn() }\n"
        "impl Widget {\n"
        "    fn set(&mut self, h: fn()) {\n"
        "        self.callback = h;\n"
        "    }\n"
        "}\n"
    )
    out = _harvest_callback_file(tree, src)
    assert any(r[1] == "Widget::callback" and r[2] == "h" for r in out["regs"])
