# SPDX-License-Identifier: MIT
"""Shell, CMake, YAML and JSON reach the index — and each gets what its file type is.

1.1.0, sumac's ask, answered by SPLITTING IT. The request was "index shell, CMake, YAML
and JSON". Three of those four words mean different things:

| file type | has a function concept? | what the index gives it |
|---|---|---|
| `.sh` / `.bash` | yes — `function_definition` | `memberdef` rows, docs from the `#` block |
| `CMakeLists.txt` / `.cmake` | yes — `function_def`, `macro_def` | `memberdef` rows, macro recorded as a macro |
| `.yaml` / `.yml` / `.json` | **no** | a `path` row: present in the file set, no symbols |

WHY YAML AND JSON GET NO SYMBOLS. Their grammars offer `block_mapping_pair` and `pair`.
Writing those as `memberdef` rows would put every `steps:` key of every workflow file into
the same namespace that answers `dossier("my_function")` — thousands of rows that are not
symbols, drowning the ones that are. What those files need is to be VISIBLE: findable by
name, and named by the miss report when a query finds nothing.

THE ROUTER IS CAPABILITY-GATED. `parse_tree` raises `ValueError: unknown language key` for
a grammar the installed wheel lacks, so a `.sh` file routed to a bash grammar that is not
compiled in would take the build down mid-parse. With the published substrate the route
resolves to no grammar at all, the file is registered and searchable, and it carries no
symbols — the same outcome as YAML, and the degrade this release is designed around.

@brief The script and data front ends: routing, claims, and the rows each produces.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew import substrate
from clew.harvest import _ts_language_for
from clew.synth import claims, emit_definitions, register_paths

_SCHEMA = Path(__file__).resolve().parent.parent / "clew" / "data" / "doxygen_schema.sql"

_SH = """#!/bin/bash
# Deploy the built artefact.
deploy() {
  rsync -a build/ "$1"
}
"""

_CMAKE = """# Register one firmware image.
function(add_firmware NAME)
  add_executable(${NAME} src/main.c)
endfunction()

# Paste the warning flags into the caller.
macro(strict_warnings TARGET)
  target_compile_options(${TARGET} PRIVATE -Wall)
endmacro()
"""


## @brief A repo holding one file of each claimed type, and an empty schema database.
## @version 1
@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "scripts" / "deploy.sh").write_text(_SH, encoding="utf-8")
    (root / "CMakeLists.txt").write_text(_CMAKE, encoding="utf-8")
    (root / "config.yaml").write_text("name: ci\njobs:\n  build:\n    runs-on: linux\n")
    (root / "data.json").write_text('{"a": 1}\n')
    (root / "src" / "main.c").write_text("int main(void) { return 0; }\n")

    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()
    return db, root


## @brief The files in the index's file set.
## @version 1
def _paths(db: Path) -> set[str]:
    conn = sqlite3.connect(str(db))
    try:
        return {r[0] for r in conn.execute("SELECT name FROM path WHERE type = 1")}
    finally:
        conn.close()


## @brief Every memberdef name mapped to its kind.
## @version 1
def _members(db: Path) -> dict[str, str]:
    conn = sqlite3.connect(str(db))
    try:
        return dict(conn.execute("SELECT name, kind FROM memberdef"))
    finally:
        conn.close()


def test_a_shell_script_routes_to_the_bash_grammar() -> None:
    """@brief `.sh` resolves a grammar. @version 1"""
    if not substrate.has_language("bash"):
        pytest.skip("substrate has no bash grammar; see .claude/tmp/substrate-fork.md")
    grammar = _ts_language_for("scripts/deploy.sh")
    assert grammar is not None
    assert grammar.key == "bash"


def test_the_cmake_file_name_routes_even_though_its_extension_is_txt() -> None:
    """`CMakeLists.txt` is named, not suffixed — and `.txt` must NOT route to CMake, or
    every README.txt in the tree would be parsed as a build script.

    @brief The CMake file name routes; a plain `.txt` does not. @version 1
    """
    if not substrate.has_language("cmake"):
        pytest.skip("substrate has no cmake grammar; see .claude/tmp/substrate-fork.md")
    named = _ts_language_for("CMakeLists.txt")
    assert named is not None and named.key == "cmake"
    assert _ts_language_for("src/CMakeLists.txt") is not None
    assert _ts_language_for("notes.txt") is None
    assert _ts_language_for("requirements.txt") is None


def test_a_missing_grammar_routes_to_nothing_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE DEGRADE, pinned. `parse_tree` raises ValueError for an unknown key, so the
    router must refuse the route rather than hand the build a grammar it cannot use.

    @brief An absent optional grammar resolves to None. @version 1
    """
    monkeypatch.setattr(substrate, "has_language", lambda key: key not in {"bash", "cmake"})
    assert _ts_language_for("scripts/deploy.sh") is None
    assert _ts_language_for("CMakeLists.txt") is None
    ## The always-present grammars are NOT gated: a wheel without them is a broken
    ## install, and failing loudly is correct there.
    assert _ts_language_for("src/main.c") is not None


def test_every_new_file_type_is_claimed_for_the_file_set() -> None:
    """@brief The front end claims shell, CMake, YAML and JSON. @version 1"""
    for rel in (
        "scripts/deploy.sh",
        "scripts/lib.bash",
        "CMakeLists.txt",
        "cmake/toolchain.cmake",
        "config.yaml",
        ".github/workflows/ci.yml",
        "data.json",
    ):
        assert claims(rel), rel
    ## Not claimed: doxygen reads C, and markdown is prose, not a symbol-bearing file.
    assert not claims("src/main.c")
    assert not claims("README.md")


def test_the_data_files_are_in_the_file_set_with_no_symbols(repo: tuple[Path, Path]) -> None:
    """@brief YAML and JSON are registered and carry no memberdef rows. @version 1"""
    db, root = repo
    scanned = ["config.yaml", "data.json", "src/main.c"]

    register_paths(db, scanned)

    assert _paths(db) == {"config.yaml", "data.json"}
    emit_definitions(db, root, None)
    assert _members(db) == {}


def test_shell_and_cmake_definitions_become_rows(repo: tuple[Path, Path]) -> None:
    """The end-to-end path: registration, the shared harvest's dispatch, and the writer.

    @brief A shell function and a CMake function and macro are written as rows. @version 1
    """
    db, root = repo
    missing = substrate.missing_languages(("bash", "cmake"))
    if missing:
        pytest.skip(f"substrate lacks {missing}; see .claude/tmp/substrate-fork.md")

    register_paths(db, ["scripts/deploy.sh", "CMakeLists.txt", "config.yaml"])
    emit_definitions(db, root, None)

    members = _members(db)
    assert members == {
        "deploy": "function",
        "add_firmware": "function",
        "strict_warnings": "macro definition",
    }


def test_the_shell_doc_block_reaches_the_row(repo: tuple[Path, Path]) -> None:
    """@brief The `#` block above a shell function becomes its brief. @version 1"""
    db, root = repo
    if not substrate.has_language("bash"):
        pytest.skip("substrate has no bash grammar; see .claude/tmp/substrate-fork.md")

    register_paths(db, ["scripts/deploy.sh"])
    emit_definitions(db, root, None)

    conn = sqlite3.connect(str(db))
    try:
        brief = conn.execute(
            "SELECT briefdescription FROM memberdef WHERE name = 'deploy'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert "Deploy the built artefact." in brief


def test_a_file_merely_ending_in_the_cmake_name_is_not_cmake() -> None:
    """THE SUFFIX TRAP. Both the router and `claims` match `CMakeLists.txt` by name, and the
    cheap way to express that in a suffix table — `endswith("cmakelists.txt")` — also
    matches `oldcmakelists.txt` and `vendor-cmakelists.txt`. The name is a whole path
    component, so that is what is tested.

    @brief The CMake name matches as a component, not as a suffix. @version 1
    """
    assert claims("CMakeLists.txt")
    assert claims("src/CMakeLists.txt")
    assert not claims("oldcmakelists.txt")
    assert not claims("src/vendor-CMakeLists.txt")

    if substrate.has_language("cmake"):
        assert _ts_language_for("src/CMakeLists.txt") is not None
        assert _ts_language_for("oldcmakelists.txt") is None
