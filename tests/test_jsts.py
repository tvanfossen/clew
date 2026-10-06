# SPDX-License-Identifier: MIT
"""JavaScript / TypeScript: the parse-built front end and the call dialect.

Doxygen cannot read JS/TS, so clew/synth.py writes their `path` / `memberdef` /
`compounddef` / `member` / `compoundref` rows from the parse (dg_source='parse'), and
clew/jsast.py supplies definitions and call sites. A repo with nothing doxygen reads skips
doxygen entirely; a mixed repo gets both front ends in one index.

@brief Tests for the JS/TS front end, call dialect and self-edge rule.
@version 1
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import lang_parsing_substrate as lps
import pytest

from clew.call_edges import _self_directed_sites
from clew.cli import _build_argparser, _run_pipeline
from clew.jsast import harvest_calls, harvest_definitions, is_js_tree
from clew.synth import claims, module_of, render_doc

TS = b"""\
/**
 * Formats strings.
 *
 * Handles a Map<string, number> & friends.
 * @version 3
 * @req REQ-JS-001
 */
export class Formatter extends Base implements Shape {
  /** Trims the input. @version 1 */
  trim(s: string): string { return this.clean(s).trim(); }

  clean = (s: string): string => normalize(s);

  static make(): Formatter { return new Formatter(); }
}

/** A base class. */
export class Base {}

/** Normalizes. @version 2 */
export function normalize(s: string): string { return s; }

export const run = () => {
  const f = new Formatter();
  return [1, 2].map(normalize).length + f.trim(" x ").length;
};

interface Shape { area(): number; }
setTimeout(() => normalize("x"), 1);
"""


def _tree(key: str, src: bytes):
    return lps.parse_tree(key, src)


# ─── definitions ─────────────────────────────────────────────────────────────


def test_definitions_functions_and_classes():
    out = harvest_definitions(_tree("typescript", TS), TS)
    functions = {(f["cls"], f["name"]): f for f in out["functions"]}
    assert set(functions) == {
        ("Formatter", "trim"),
        ("Formatter", "clean"),
        ("Formatter", "make"),
        ("", "normalize"),
        ("", "run"),
    }, "anonymous callbacks are not definitions"
    assert functions[("Formatter", "make")]["static"] == 1
    assert functions[("", "normalize")]["ret"] == "string"
    assert functions[("", "run")]["line"] == 23 and functions[("", "run")]["end"] == 26
    classes = {c["name"]: c for c in out["classes"]}
    assert classes["Formatter"]["bases"] == ["Base", "Shape"]
    assert classes["Shape"]["kind"] == "interface"
    assert "Formats strings." in classes["Formatter"]["doc"]


def test_definitions_in_plain_javascript_and_tsx():
    js = b"/** Adds. */\nfunction add(a, b) { return a + b; }\nmodule.exports = { add };\n"
    assert [f["name"] for f in harvest_definitions(_tree("javascript", js), js)["functions"]] == [
        "add"
    ]
    tsx = b"export function App() { return <div>{x}</div>; }\n"
    assert [f["name"] for f in harvest_definitions(_tree("tsx", tsx), tsx)["functions"]] == ["App"]


def test_is_js_tree():
    assert is_js_tree(_tree("javascript", b"x;"))
    assert not is_js_tree(_tree("python", b"x = 1\n"))


# ─── call sites ──────────────────────────────────────────────────────────────


def test_call_sites_in_fold_shape():
    sites = harvest_calls(_tree("typescript", TS), TS, "ast", "ast_member", "binding")
    as_set = {tuple(s) for s in sites}
    assert ("clean", 10, "ast_member", "Formatter.clean", "") in as_set, "this.m() is qualified"
    # `this.clean(s).trim()` is String's trim: no receiver can be named, so the site carries
    # none and the fold grades it fuzzy (a same-named function exists, unconfirmed), as it
    # does for every unverifiable member call in C and Python.
    assert ("trim", 10, "ast_member", "", "") in as_set
    assert ("normalize", 12, "ast", "", "") in as_set
    assert ("constructor", 14, "ast_member", "Formatter.constructor", "") in as_set, "new C()"
    assert ("trim", 25, "ast_member", "", "f") in as_set, "obj.m() carries its receiver"
    assert ("normalize", 25, "binding") in as_set, "a function passed by name is a binding"


def test_self_edge_rule_for_js_methods():
    src = b"""\
class A {
  m() { m(); this.m(); }
}
function f() { f(); }
"""
    sites = set(_self_directed_sites(_tree("javascript", src), src))
    assert ("m", 2) in sites, "this.m() inside m is self-directed"
    assert sites == {("m", 2), ("f", 4)}, (
        "a bare m() in a method is NOT the method (no implicit this)"
    )


# ─── rendering ───────────────────────────────────────────────────────────────


def test_render_doc_matches_doxygen_shapes_and_escapes():
    raw = (
        "/**\n * Formats strings.\n *\n * Handles a Map<string, number> & friends.\n"
        " * @version 3\n * @req REQ-JS-001\n */"
    )
    brief, detail = render_doc(raw)
    assert brief == "<para>Formats strings.</para>"
    assert "<para>Handles a Map&lt;string, number&gt; &amp; friends.</para>" in detail
    assert '<simplesect kind="version"><para>3</para>' in detail
    assert "<para>@req REQ-JS-001</para>" in detail
    from clew.query._common import extract_version, strip_xml

    assert extract_version(detail) == "3"
    assert "Map&lt;string" in strip_xml(detail), "escaped text survives the markup stripper"


def test_render_doc_one_line_and_empty():
    assert render_doc("/** Adds one. @version 1 */")[0] == "<para>Adds one.</para>"
    assert render_doc("") == ("", "")


def test_module_and_claims():
    assert module_of("src/util/strings.ts") == "src.util.strings"
    assert module_of("web/App.test.tsx") == "web.App.test"
    assert claims("a/b.mjs") and claims("x.TSX") and not claims("a.py")


# ─── builds ──────────────────────────────────────────────────────────────────


def _write(root: Path, rel: str, text: str | bytes) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text if isinstance(text, bytes) else text.encode())


def _build(repo: Path, out: Path) -> sqlite3.Connection:
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    return sqlite3.connect(out)


def test_js_only_build_needs_no_doxygen(tmp_path, monkeypatch, caplog):
    """No file doxygen reads, so doxygen is never invoked — it need not even be installed."""
    from clew import doxygen as doxygen_module

    monkeypatch.setattr(doxygen_module.shutil, "which", lambda _name: None)
    repo = tmp_path / "repo"
    _write(repo, "src/util/strings.ts", TS)
    _write(
        repo, "src/app.js", 'import { run } from "./util/strings";\nfunction main() { run(); }\n'
    )
    _write(repo, "README.md", "# demo\n")
    conn = _build(repo, tmp_path / "clew.db")

    rows = dict(conn.execute("SELECT definition, dg_source FROM memberdef WHERE kind='function'"))
    assert rows == {
        "src.util.strings.Formatter.trim": "parse",
        "src.util.strings.Formatter.clean": "parse",
        "src.util.strings.Formatter.make": "parse",
        "src.util.strings.normalize": "parse",
        "src.util.strings.run": "parse",
        "src.app.main": "parse",
    }
    compounds = dict(conn.execute("SELECT name, kind FROM compounddef"))
    assert compounds["src::util::strings::Formatter"] == "class"
    assert compounds["src::util::strings::Shape"] == "interface"
    bases = set(
        conn.execute(
            "SELECT b.name, d.name FROM compoundref r JOIN compounddef b ON b.rowid=r.base_rowid "
            "JOIN compounddef d ON d.rowid=r.derived_rowid"
        )
    )
    assert ("src::util::strings::Base", "src::util::strings::Formatter") in bases
    members = {
        r[0]
        for r in conn.execute(
            "SELECT m.name FROM member x JOIN memberdef m ON m.rowid=x.memberdef_rowid "
            "JOIN compounddef c ON c.rowid=x.scope_rowid WHERE c.name LIKE '%::Formatter'"
        )
    }
    assert members == {"trim", "clean", "make"}
    edges = set(
        conn.execute(
            "SELECT a.name, b.name, e.source FROM call_edges e "
            "JOIN memberdef a ON a.rowid=e.caller_rowid JOIN memberdef b ON b.rowid=e.callee_rowid"
        )
    )
    assert ("main", "run", "ast") in edges
    assert ("trim", "clean", "ast_member") in edges
    assert ("run", "normalize", "binding") in edges
    assert "doxygen: skipped" in caplog.text


@pytest.mark.skipif(shutil.which("doxygen") is None, reason="the C half needs doxygen")
def test_mixed_repo_gets_both_front_ends(tmp_path):
    repo = tmp_path / "repo"
    _write(repo, "native/add.c", "/** @brief Adds. */\nint add(int a, int b) { return a + b; }\n")
    _write(
        repo,
        "web/ui.ts",
        "/** Renders. */\nexport function render(): void { paint(); }\nfunction paint(): void {}\n",
    )
    conn = _build(repo, tmp_path / "clew.db")
    sources = dict(conn.execute("SELECT name, dg_source FROM memberdef WHERE kind='function'"))
    assert sources == {"add": "doxygen", "render": "parse", "paint": "parse"}
    edges = set(
        conn.execute(
            "SELECT a.name, b.name FROM call_edges e JOIN memberdef a ON a.rowid=e.caller_rowid "
            "JOIN memberdef b ON b.rowid=e.callee_rowid"
        )
    )
    assert ("render", "paint") in edges


def test_init_doctor_does_not_require_doxygen_for_a_js_only_repo(tmp_path, monkeypatch):
    from clew import init_command

    monkeypatch.setattr(init_command.shutil, "which", lambda _name: None)
    _write(tmp_path, "src/a.ts", "export const f = () => 1;\n")
    _write(tmp_path, "node_modules/dep/x.c", "int x;\n")
    _write(tmp_path, "README.md", "# demo\n")
    check = init_command._check_doxygen(tmp_path)
    assert check.status == init_command.CHECK_OK and "not required" in check.detail
    _write(tmp_path, "native/a.c", "int y;\n")
    assert init_command._check_doxygen(tmp_path).status == init_command.CHECK_FAIL
