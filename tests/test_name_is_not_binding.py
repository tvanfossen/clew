# SPDX-License-Identifier: MIT
"""A name that merely matches is not a binding (round 5, agent C's audit W1-W5).

`_ast_record_call_edge` states the rule: "A NAME IS NOT EVIDENCE OF LINKAGE". Agent C's read-only
audit (vetted 2026-11-17, every probe rebuilt) found five resolution paths that still take a
spelling as a binding and mint `confidence='resolved'`. Each case here pairs the false edge with a
guard: the real call of the same shape that must keep its edge, because a fix that drops both has
only moved the error.

@brief Tests that locals, parameters and same-named things elsewhere do not make edges.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.cli import _build_argparser, _run_pipeline

_FILES = {
    ## W2 (Python): a bare call through a PARAMETER or an assigned local is not a call of the
    ## same-named function; a nested `def` and an imported name are.
    "py/__init__.py": "",
    "py/cb.py": 'def finish():\n    """The function."""\n    return 1\n',
    "py/run.py": (
        "from py.cb import finish\n\n\n"
        "def go(finish):\n"
        '    """Calls its parameter."""\n'
        "    return finish()\n\n\n"
        "def assigned():\n"
        '    """Calls a local it assigned."""\n'
        "    finish = make()\n"
        "    return finish()\n\n\n"
        "def make():\n"
        '    """Makes."""\n'
        "    return finish\n\n\n"
        "def imported():\n"
        '    """Calls the imported function: a real call."""\n'
        "    return finish()\n"
    ),
    ## W2 (TypeScript) and W3 (an argument): a parameter is not a function reference; a
    ## function-valued const and a real function passed along are.
    "src/cb.ts": "export function done(): number { return 1; }\n",
    "src/cfg.ts": (
        "export function config(): number { return 3; }\n\n"
        "export function setup(x: unknown): unknown { return x; }\n\n"
        "export function start(config: number): unknown {\n  return setup(config);\n}\n\n"
        "export function register(): unknown {\n  return setup(config);\n}\n"
    ),
    "src/run.ts": (
        "import { done } from './cb';\n\n"
        "export function run(done: () => number): number {\n  return done();\n}\n\n"
        "export function real(): number {\n  return done();\n}\n\n"
        "export function closure(): number {\n"
        "  const helper = () => 1;\n"
        "  return helper();\n"
        "}\n"
    ),
    ## W4 (TypeScript): a receiver named like an object literal in ANOTHER file is not that
    ## object; in the object's own file it is.
    "src/api.ts": (
        "export const api = { get: (): number => 1 };\n\n"
        "export function useIt(): number {\n  return api.get();\n}\n"
    ),
    "src/fetch.ts": (
        "interface Client { get(): number; }\n\n"
        "export function fetchIt(api: Client): number {\n  return api.get();\n}\n"
    ),
    ## W5 (Python): an absolute import names a module on an IMPORT ROOT — the repository root,
    ## the parent of a top-level package, or the importing script's own directory — never a
    ## same-named file anywhere in the tree.
    "app/__init__.py": "",
    "app/main.py": 'import json\n\n\ndef read(t):\n    """Reads."""\n    return json.loads(t)\n',
    "tests/fakes/json.py": 'def loads(s):\n    """A fake."""\n    return s\n',
    "tests/helper.py": 'def assist():\n    """A helper beside the tests."""\n    return 1\n',
    "tests/test_use.py": (
        'import helper\n\n\ndef test_it():\n    """Uses it."""\n    assert helper.assist() == 1\n'
    ),
    ## Found by measuring W1-W5 on the four run repos (each a real call the first cut dropped):
    ## a subscript target binds nothing; a wrapper-bound const is a function.
    "py/keys.py": (
        'def rel_key(p):\n    """Key."""\n    return p\n\n\n'
        "def enumerate_tree(paths):\n"
        '    """Assigns INTO a dict; `rel_key` is not a local."""\n'
        "    found = {}\n"
        "    for path in paths:\n"
        "        found[rel_key(path)] = path\n"
        "    return found\n"
    ),
    "src/hooks.ts": (
        "declare function useCallback<T>(fn: T, deps: unknown[]): T;\n\n"
        "export function About(): number {\n"
        "  const openURL = useCallback((url: string) => url.length, []);\n"
        "  return openURL('x');\n"
        "}\n"
    ),
    ## A destructured `require` inside a function is an IMPORT (found vetting mattermost losses).
    "scripts/bucket.js": "function webhookBucket(n) { return n; }\nmodule.exports = { webhookBucket };\n",
    "scripts/report.js": (
        "function reportTitle(n) {\n"
        "  const { webhookBucket } = require('./bucket');\n"
        "  return webhookBucket(n);\n"
        "}\n"
        "module.exports = { reportTitle };\n"
    ),
    ## W1 (C++): a LOCAL named like some class's member is not that member.
    "cpp/eng.h": (
        "struct EngA { int run(); };\n"
        "struct EngB { int run(); };\n"
        "struct Holder { EngA *engine; int go(); };\n"
        "int use_local();\n"
        "int use_param(EngB *engine);\n"
        "int use_cast(void *p);\n"
        "int ns_cast(void *p);\n"
        "int in_lambda(void *p);\n"
    ),
    "cpp/eng.cpp": (
        '#include "eng.h"\n'
        "int EngA::run() { return 1; }\n"
        "int EngB::run() { return 2; }\n"
        "int Holder::go() { return engine->run(); }\n"
        "int use_local() {\n"
        "    EngB *engine = new EngB();\n"
        "    return engine->run();\n"
        "}\n"
        "int use_param(EngB *engine) { return engine->run(); }\n"
        "int use_cast(void *p) {\n"
        "    auto *engine = static_cast<EngB *>(p);\n"
        "    return engine->run();\n"
        "}\n"
        "namespace ns { struct Orch { int clear(); }; int Orch::clear() { return 0; } }\n"
        "int ns_cast(void *p) {\n"
        "    auto *o = static_cast<ns::Orch *>(p);\n"
        "    return o->clear();\n"
        "}\n"
        "int in_lambda(void *p) {\n"
        "    auto fn = [](void *ud) { auto *o = static_cast<ns::Orch *>(ud); return o->clear(); };\n"
        "    return fn(p);\n"
        "}\n"
    ),
}


## @brief The fixture repository, indexed.
## @param tmp_path_factory Pytest's factory.
## @return The index path.
## @version 1
@pytest.fixture(scope="module")
def db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """@brief Build. @return Index."""
    root = tmp_path_factory.mktemp("names")
    repo = root / "repo"
    for rel, text in _FILES.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    out = root / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    return out


def _pairs(db: Path) -> set[tuple[str, str]]:
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT a.name, b.name FROM call_edges c JOIN memberdef a ON a.rowid = c.caller_rowid "
        "JOIN memberdef b ON b.rowid = c.callee_rowid"
    ).fetchall()
    conn.close()
    return {(str(a).rsplit(".", 1)[-1], str(b).rsplit(".", 1)[-1]) for a, b in rows}


def test_a_python_call_through_a_parameter_or_assigned_local_is_no_edge(db: Path) -> None:
    """`def go(finish): finish()` calls whatever was passed, not `py.cb.finish`; neither does
    `finish = make(); finish()`. The imported call keeps its edge. (A nested `def` would be
    the other guard, but Python nested functions are not indexed at all — a separate gap, found
    writing this test, so no call of one can be asserted either way.)

    @brief W2 Python, with guards.
    """
    pairs = _pairs(db)
    assert ("go", "finish") not in pairs
    assert ("assigned", "finish") not in pairs
    assert ("imported", "finish") in pairs


def test_a_typescript_call_through_a_parameter_is_no_edge(db: Path) -> None:
    """Every `new Promise((resolve) => resolve(x))` and `callback()` had an inbound resolved edge
    to any function so named. A function-valued const is still a nested closure and still called.

    @brief W2 TypeScript, with guards.
    """
    pairs = _pairs(db)
    assert ("run", "done") not in pairs
    assert ("real", "done") in pairs
    assert ("closure", "helper") in pairs


def test_a_parameter_passed_as_an_argument_is_not_a_function_reference(db: Path) -> None:
    """The JS twin of `_keyword_bindings` v3: `start(config)` passes its parameter along.
    `register()` passes the module's function `config`, which IS a reference.

    @brief W3, with a guard.
    """
    pairs = _pairs(db)
    assert ("start", "config") not in pairs
    assert ("register", "config") in pairs


def _ast_callees(db: Path, caller: str) -> set[str]:
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT b.definition FROM call_edges c JOIN memberdef a ON a.rowid = c.caller_rowid "
        "JOIN memberdef b ON b.rowid = c.callee_rowid "
        "WHERE a.name = ? AND c.source != 'doxygen_sqlite'",
        (caller,),
    ).fetchall()
    conn.close()
    return {str(d) for (d,) in rows}


def test_a_local_or_parameter_named_like_a_member_does_not_take_its_type(db: Path) -> None:
    """`EngB *engine = new EngB(); engine->run()` was resolved to `EngA::run` because class
    `Holder` has a member `EngA *engine`. Inside `Holder::go`, `engine` IS that member and keeps
    its typing.

    @brief W1, with the member guard.
    """
    assert not any("EngA::run" in d for d in _ast_callees(db, "use_local"))
    assert not any("EngA::run" in d for d in _ast_callees(db, "use_param"))
    assert any("EngA::run" in d for d in _ast_callees(db, "go"))


def test_a_receiver_named_like_another_file_s_object_does_not_own_it(db: Path) -> None:
    """`fetchIt(api: Client) { api.get() }` resolved to `src/api.ts`'s `api.get`, which
    `fetch.ts` never imports. `useIt` in `api.ts` itself calls that object.

    @brief W4, with the same-file guard.
    """
    pairs = _pairs(db)
    assert ("fetchIt", "get") not in pairs
    assert ("useIt", "get") in pairs


def test_an_absolute_import_names_a_module_on_an_import_root_only(db: Path) -> None:
    """`import json; json.loads()` resolved to `tests/fakes/json.py::loads` (agent C's W5, probe
    p4). A test's `import helper` names `tests/helper.py`, because the test's own directory is on
    `sys.path` (pytest and plain scripts alike) — that edge must stay.

    @brief W5 in clew's resolver, with the script-directory guard.
    """
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT a.name, b.name FROM call_edges c JOIN memberdef a ON a.rowid = c.caller_rowid "
        "JOIN memberdef b ON b.rowid = c.callee_rowid WHERE c.source != 'doxygen_sqlite'"
    ).fetchall()
    conn.close()
    pairs = {(str(x), str(y)) for x, y in rows}
    assert ("read", "loads") not in pairs
    assert ("test_it", "assist") in pairs


def test_a_subscript_assignment_target_binds_nothing(db: Path) -> None:
    """`found[rel_key(path)] = path` assigns into `found`; `rel_key` stays a call. Found by the
    W1-W5 measurement on clew's own tree (`enumerate_tree -> rel_key` was dropped).

    @brief Only names and name patterns are bound.
    """
    assert ("enumerate_tree", "rel_key") in _pairs(db)


def test_a_wrapper_bound_const_is_a_function_not_a_shadow(db: Path) -> None:
    """`const openURL = useCallback(() => ...)` is the closure the index holds (the general
    wrapper rule); calling it is a call. Found by the W1-W5 measurement on mattermost-mobile.

    @brief The shadow rule reads function values as the definitions do.
    """
    assert ("About", "openURL") in _pairs(db)


def test_a_typed_local_or_parameter_resolves_through_its_declared_class(db: Path) -> None:
    """`EngB *engine = new EngB(); engine->run()` and `use_param(EngB *engine)` call
    `EngB::run` — the declaration states it. Found by the W1-W5 measurement on entropic, where
    blanking such receivers lost edges the old member typing had right by coincidence.

    @brief W1's positive half.
    """
    assert any("EngB::run" in d for d in _ast_callees(db, "use_local"))
    assert any("EngB::run" in d for d in _ast_callees(db, "use_param"))


def test_a_destructured_require_binds_the_module_s_function(db: Path) -> None:
    """`const { webhookBucket } = require('./bucket')` inside a function binds that module's
    function — calling it is a call. Found vetting the mattermost losses of the W1-W5 change
    (`reportTitleForIdentity -> webhookBucketForReportName`).

    @brief require() is an import, not a value.
    """
    assert ("reportTitle", "webhookBucket") in _pairs(db)


def test_an_auto_local_initialised_by_a_cast_takes_the_cast_s_type(db: Path) -> None:
    """`auto *engine = static_cast<EngB *>(p); engine->run()` calls `EngB::run`: the cast states
    the type. Found vetting the entropic losses of the W1-W5 change (`attach -> register_hook`
    through `auto* reg = static_cast<HookRegistry*>(...)`).

    @brief static_cast / dynamic_cast / reinterpret_cast state a type.
    """
    assert any("EngB::run" in d for d in _ast_callees(db, "use_cast"))


def test_a_namespaced_cast_and_a_lambda_s_local_are_typed_too(db: Path) -> None:
    """`static_cast<ns::Orch *>(p)` names `ns::Orch` (the namespace inside the template argument
    once split the cast's own name); a lambda's local is a local of the function it sits in.
    Found vetting entropic (`auto* orch = static_cast<entropic::ModelOrchestrator*>(ud)` inside a
    lambda, `init_engine_and_interfaces -> clear_all_prompt_caches`).

    @brief Namespaced casts; locals inside lambdas.
    """
    assert any("Orch::clear" in d for d in _ast_callees(db, "ns_cast"))
    assert any("Orch::clear" in d for d in _ast_callees(db, "in_lambda"))
