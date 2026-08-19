# SPDX-License-Identifier: MIT
"""Tests for clew/rustdoc.py — the rustdoc-JSON analog of doxygen.py.

The unit tests below exercise the pure functions (type rendering, brief
extraction, JSON-to-symbol resolution) against hand-built rustdoc JSON
fragments, no subprocess involved. `test_run_rustdoc_against_real_crate`
is the one integration test: it actually shells out to `cargo +nightly
rustdoc` against `tests/data/rustsample/`, and is skipped when that
toolchain isn't available — mirroring how `test_ast_symbols.py` skips
when tree_sitter's C/C++ grammars aren't importable.

@brief Tests for rustdoc JSON ingestion.
@version 1
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from clew.errors import RustdocUnavailableError
from clew.rustdoc import (
    _brief,
    _discover_targets,
    _find_rustdoc_json,
    _render_argsstring,
    _render_type,
    _symbols_from_json,
    has_cargo_manifest,
    run_rustdoc,
)

RUSTSAMPLE = Path(__file__).resolve().parent / "data" / "rustsample"


def _nightly_rustdoc_available() -> bool:
    if shutil.which("cargo") is None:
        return False
    proc = subprocess.run(["cargo", "+nightly", "--version"], capture_output=True, text=True)
    return proc.returncode == 0


pytestmark_nightly = pytest.mark.skipif(
    not _nightly_rustdoc_available(),
    reason="needs cargo + a nightly toolchain (rustup toolchain install nightly)",
)


def test_has_cargo_manifest_true_for_a_cargo_repo(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\n", encoding="utf-8")
    assert has_cargo_manifest(tmp_path) is True


def test_has_cargo_manifest_false_without_one(tmp_path: Path) -> None:
    assert has_cargo_manifest(tmp_path) is False


def test_render_type_primitive():
    assert _render_type({"primitive": "i32"}) == "i32"


def test_render_type_none_is_unit():
    assert _render_type(None) == "()"


def test_render_type_borrowed_ref():
    inner = {"borrowed_ref": {"is_mutable": False, "type": {"primitive": "str"}}}
    assert _render_type(inner) == "&str"


def test_render_type_borrowed_mut_ref():
    inner = {"borrowed_ref": {"is_mutable": True, "type": {"primitive": "i32"}}}
    assert _render_type(inner) == "&mut i32"


def test_render_type_resolved_path():
    inner = {"resolved_path": {"path": "std::collections::HashMap"}}
    assert _render_type(inner) == "std::collections::HashMap"


def test_render_type_unrecognized_shape_is_a_placeholder_not_an_error():
    assert _render_type({"impl_trait": []}) == "?"


def test_render_argsstring_joins_named_params():
    sig = {"inputs": [["left", {"primitive": "i32"}], ["right", {"primitive": "i32"}]]}
    assert _render_argsstring(sig) == "(i32 left, i32 right)"


def test_render_argsstring_empty_for_no_params():
    assert _render_argsstring({"inputs": []}) == "()"


def test_brief_is_the_first_nonblank_line():
    assert _brief("Adds two numbers.\n\nMore detail here.") == "Adds two numbers."


def test_brief_skips_leading_blank_lines():
    assert _brief("\n\nActual brief.\nrest") == "Actual brief."


def test_brief_none_docs_is_empty_string():
    assert _brief(None) == ""


def _item(
    *,
    name,
    kind,
    span=("src/lib.rs", 1, 1, 3, 2),
    visibility="public",
    docs=None,
    sig=None,
):
    inner: dict = {}
    if kind == "function":
        inner["function"] = {"sig": sig or {"inputs": [], "output": None}}
    elif kind == "static":
        inner["static"] = {"type": {"primitive": "i32"}, "expr": "3"}
    elif kind == "constant":
        inner["constant"] = {"type": {"primitive": "i32"}, "expr": "0"}
    return {
        "name": name,
        "visibility": visibility,
        "docs": docs,
        "span": (
            None
            if span is None
            else {
                "filename": span[0],
                "begin": [span[1], span[2]],
                "end": [span[3], span[4]],
            }
        ),
        "inner": inner,
    }


def test_symbols_from_json_extracts_a_public_function():
    doc = {"index": {"0": _item(name="add", kind="function")}, "paths": {}}
    symbols = _symbols_from_json(doc, "0")
    assert len(symbols) == 1
    sym = symbols[0]
    assert sym.name == "add"
    assert sym.kind == "function"
    assert sym.file == "src/lib.rs"
    assert sym.static == 0


def test_symbols_from_json_private_item_is_marked_static():
    doc = {"index": {"0": _item(name="helper", kind="function", visibility="default")}, "paths": {}}
    assert _symbols_from_json(doc, "0")[0].static == 1


def test_symbols_from_json_skips_items_with_no_span():
    doc = {"index": {"0": _item(name="from", kind="function", span=None)}, "paths": {}}
    assert _symbols_from_json(doc, "0") == []


def test_symbols_from_json_skips_unmodeled_kinds():
    doc = {
        "index": {
            "0": {
                "name": "Counter",
                "visibility": "public",
                "docs": None,
                "span": {"filename": "src/lib.rs", "begin": [1, 1], "end": [3, 2]},
                "inner": {"struct": {}},
            }
        },
        "paths": {},
    }
    assert _symbols_from_json(doc, "0") == []


def test_symbols_from_json_maps_static_and_constant_to_variable_kind():
    doc = {
        "index": {
            "0": _item(name="MAX", kind="static"),
            "1": _item(name="MIN", kind="constant"),
        },
        "paths": {},
    }
    symbols = {s.name: s for s in _symbols_from_json(doc, "0")}
    assert symbols["MAX"].kind == "variable"
    assert symbols["MIN"].kind == "variable"


def test_discover_targets_documents_both_lib_and_same_named_bin(tmp_path: Path) -> None:
    """RUSTDOC_INTEGRATION_FEEDBACK.md, finding 1: `knots` and `tools_sqc` both pair a
    `[lib]` with a same-named `[[bin]]`, and the old lib-instead-of-bin selection silently
    dropped every module reachable only from the bin (`main.rs`, CLI parsing, config
    loading, output formatting) with no error — `cargo metadata` succeeds either way, so
    nothing in the build log said a target was skipped. This crate reproduces that exact
    shape and asserts both targets come back.

    @brief A package with both a lib and a same-named bin documents both, not just the lib.
    @return None.
    @version 1
    """
    if shutil.which("cargo") is None:
        pytest.skip("needs cargo")
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "dual"\nversion = "0.1.0"\nedition = "2021"\n\n'
        '[lib]\nname = "dual"\n\n[[bin]]\nname = "dual"\npath = "src/main.rs"\n',
        encoding="utf-8",
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "lib.rs").write_text("pub fn helper() {}\n", encoding="utf-8")
    (src / "main.rs").write_text("fn main() {}\n", encoding="utf-8")

    targets = _discover_targets(tmp_path)

    kinds = {(t.name, t.kind) for t in targets}
    assert kinds == {("dual", "lib"), ("dual", "bin")}, (
        f"a package with both a lib and a same-named bin must document both; got {kinds}"
    )


def test_run_rustdoc_refuses_a_non_cargo_repo(tmp_path: Path) -> None:
    if not _nightly_rustdoc_available():
        pytest.skip("needs cargo + a nightly toolchain")
    with pytest.raises(RustdocUnavailableError):
        run_rustdoc(tmp_path, tmp_path / "out.db")


@pytestmark_nightly
def test_run_rustdoc_against_real_crate(tmp_path: Path) -> None:
    """The end-to-end contract: a real `cargo +nightly rustdoc` run against a
    real crate lands a doxygen-shaped database with the right path/memberdef
    rows — the same shape `tests/richdb.py` hand-makes for the C fixture.
    """
    db_path = tmp_path / "rustdoc.db"
    result = run_rustdoc(RUSTSAMPLE, db_path)
    assert result == db_path
    conn = sqlite3.connect(str(db_path))
    try:
        names = {row[0] for row in conn.execute("SELECT name FROM memberdef")}
        assert {"add", "helper", "MAX_RETRIES"} <= names

        brief = conn.execute(
            "SELECT briefdescription FROM memberdef WHERE name = 'add'"
        ).fetchone()[0]
        assert brief == "Adds two numbers together."

        add_static, helper_static = (
            conn.execute("SELECT static FROM memberdef WHERE name = ?", (name,)).fetchone()[0]
            for name in ("add", "helper")
        )
        assert add_static == 0  # pub fn
        assert helper_static == 1  # private fn

        path_row = conn.execute(
            "SELECT p.name FROM memberdef m JOIN path p ON p.rowid = m.file_id WHERE m.name = 'add'"
        ).fetchone()
        assert path_row[0] == "src/main.rs"

        # Every downstream stage that guards with _table_exists (dispatch_edges.py)
        # still gets a real, empty compounddef table rather than a missing one.
        assert conn.execute("SELECT COUNT(*) FROM compounddef").fetchone()[0] == 0
    finally:
        conn.close()


## @brief The native target-dir layout is found.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_find_rustdoc_json_native_layout(tmp_path: Path) -> None:
    """@brief A host-target build writes to <target-dir>/doc/. @return None. @version 1"""
    doc = tmp_path / "doc"
    doc.mkdir(parents=True)
    (doc / "my_crate.json").write_text("{}", encoding="utf-8")
    assert _find_rustdoc_json(tmp_path, "my_crate") == doc / "my_crate.json"


## @brief A cross-compiled crate's JSON is found under the target triple.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_find_rustdoc_json_cross_compiled_layout(tmp_path: Path) -> None:
    """THE CASE THAT MADE THE FRONT END UNUSABLE FOR EMBEDDED RUST. cargo writes to
    `<target-dir>/<triple>/doc/` whenever it is building for a triple other than the
    host, and a crate that sets `[build] target` in `.cargo/config.toml` is doing that
    on every plain `cargo` invocation. Looking only in `<target-dir>/doc/` reported the
    output missing AFTER cargo had exited 0 and written it.

    The triple here is a real one but nothing depends on which: the layout rule is
    cargo's, not any project's.

    @brief A cross-compiled build writes under <target-dir>/<triple>/doc/.
    @return None.
    @version 1
    """
    doc = tmp_path / "thumbv7em-none-eabihf" / "doc"
    doc.mkdir(parents=True)
    (doc / "my_crate.json").write_text("{}", encoding="utf-8")
    assert _find_rustdoc_json(tmp_path, "my_crate") == doc / "my_crate.json"


## @brief Absent output refuses and names both layouts it looked in.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_find_rustdoc_json_refuses_when_absent(tmp_path: Path) -> None:
    """NAMING BOTH CANDIDATES IS THE POINT. The previous message named one path and sent
    a reader looking for a bug in cargo rather than in where we searched.

    @brief An absent JSON raises and names both layouts.
    @return None.
    @version 1
    """
    with pytest.raises(RustdocUnavailableError) as caught:
        _find_rustdoc_json(tmp_path, "my_crate")
    assert "target-triple" in str(caught.value)


## @brief Two candidates refuse rather than picking one.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_find_rustdoc_json_refuses_ambiguity(tmp_path: Path) -> None:
    """FAIL CLOSED. Two triples under one target-dir means an assumption here is wrong;
    taking the first would bury that under an index that looks fine.

    @brief Ambiguous candidates raise instead of resolving arbitrarily.
    @return None.
    @version 1
    """
    for triple in ("thumbv7em-none-eabihf", "riscv32imac-unknown-none-elf"):
        doc = tmp_path / triple / "doc"
        doc.mkdir(parents=True)
        (doc / "my_crate.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RustdocUnavailableError) as caught:
        _find_rustdoc_json(tmp_path, "my_crate")
    assert "2 candidates" in str(caught.value)
