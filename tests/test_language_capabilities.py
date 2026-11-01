# SPDX-License-Identifier: MIT
"""The published support table is checked against what each front end actually produces.

WHY A TABLE AT ALL. The README said clew "harvests symbols from C, C++, Rust, Python, JavaScript,
TypeScript, shell and CMake" — one flat list. Measured, that list hides a real difference: shell
and CMake functions are named and documented, but their CALLS are not graphed. A reader seeing
shell beside C reasonably expects "who calls this" to work for both, and for shell it never will.

WHY THIS TEST. A capability table is a claim, and claims in this repository go stale — the
language list was once prose in five places and three of them were wrong. So the table is
generated from `languages.CAPABILITIES`, and this test BUILDS a two-function fixture in every
language and asserts the measured capabilities EQUAL the declared ones, in both directions. A cell
that overclaims fails; so does one that underclaims, because an understated table is how a working
feature goes unused.

Concurrency is deliberately NOT a column: measured, it is pattern-dependent within a language, so
a yes/no cell would be wrong whichever way it was set.

@brief Tests that the declared language capabilities match what a build produces.
@version 1
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from clew import languages
from clew.cli import _build_argparser, _run_pipeline

## One file per language: `add` carries a doc comment, `run` calls `add`. Every column is then
## one query against the built index.
_FIXTURES: dict[str, dict[str, str]] = {
    "C": {
        "a.c": "/** @brief Adds. */\nint add(int a,int b){return a+b;}\nint run(void){return add(1,2);}\n"
    },
    "C++": {
        "a.cpp": "/** @brief Adds. */\nint add(int a,int b){return a+b;}\nint run(){return add(1,2);}\n"
    },
    "Rust": {
        "Cargo.toml": '[package]\nname = "demo"\nversion = "0.1.0"\nedition = "2021"\n\n[lib]\npath = "src/lib.rs"\n',
        "src/lib.rs": "/// Adds.\npub fn add(a: i32, b: i32) -> i32 { a + b }\npub fn run() -> i32 { add(1, 2) }\n",
    },
    "Python": {
        "a.py": 'def add(a, b):\n    """Adds."""\n    return a + b\n\n\ndef run():\n    return add(1, 2)\n'
    },
    "JavaScript": {
        "a.js": "/** Adds. */\nfunction add(a,b){return a+b;}\nfunction run(){return add(1,2);}\n"
    },
    "TypeScript": {
        "a.ts": "/** Adds. */\nexport function add(a:number,b:number){return a+b;}\nexport function run(){return add(1,2);}\n"
    },
    "shell": {"a.sh": "# Adds.\nadd() { echo $(( $1 + $2 )); }\nrun() { add 1 2; }\n"},
    "CMake": {
        "x.cmake": '# Adds.\nfunction(add a b)\n  math(EXPR r "${a}+${b}")\nendfunction()\nfunction(run)\n  add(1 2)\nendfunction()\n'
    },
}

## The front ends whose build needs a toolchain this machine may not have.
_NEEDS = {"Rust": "cargo", "C": "doxygen", "C++": "doxygen"}


## @brief Build a fixture and report which capabilities it produced.
## @param tmp_path Directory to build in.
## @param files Relative path to file text.
## @return The capability keys the built index shows.
## @version 1
def _measure(tmp_path: Path, files: dict[str, str]) -> set[str]:
    """@brief Build one fixture and read the capability columns off the index.
    @return Measured capability keys.
    @version 1
    """
    repo = tmp_path / "repo"
    for rel, text in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    conn = sqlite3.connect(out)
    names = {n for (n,) in conn.execute("SELECT name FROM memberdef")}
    calls = conn.execute(
        "SELECT count(*) FROM call_edges e JOIN memberdef a ON a.rowid = e.caller_rowid "
        "JOIN memberdef b ON b.rowid = e.callee_rowid WHERE a.name = 'run' AND b.name = 'add'"
    ).fetchone()[0]
    brief = conn.execute("SELECT briefdescription FROM memberdef WHERE name = 'add'").fetchone()
    found = set()
    if {"add", "run"} <= names:
        found.add("symbols")
    if calls:
        found.add("calls")
    if brief and (brief[0] or "").strip():
        found.add("docs")
    return found


## @brief Every harvested language has a fixture, so none escapes the check.
## @return None.
## @version 1
def test_every_harvested_language_has_a_capability_fixture() -> None:
    """A LANGUAGE ADDED TO THE ROUTERS WITHOUT A FIXTURE WOULD BE PUBLISHED UNCHECKED. This fails
    instead, naming it.

    @brief Fixture coverage equals the harvested set.
    @return None.
    @version 1
    """
    assert set(_FIXTURES) == set(languages.HARVESTED), (
        f"fixtures {sorted(_FIXTURES)} != harvested {sorted(languages.HARVESTED)}"
    )
    assert set(languages.CAPABILITIES) == set(languages.HARVESTED)


@pytest.mark.parametrize("language", sorted(_FIXTURES))
def test_declared_capabilities_match_what_a_build_produces(tmp_path: Path, language: str) -> None:
    """BOTH DIRECTIONS. An overclaimed cell sends a reader to a feature that is not there; an
    underclaimed one hides a feature that is.

    @brief The declaration equals the measurement.
    @return None.
    @version 1
    """
    tool = _NEEDS.get(language)
    if tool and shutil.which(tool) is None:
        pytest.skip(f"the {language} front end needs {tool}, which is not installed here")
    measured = _measure(tmp_path, _FIXTURES[language])
    declared = set(languages.CAPABILITIES[language])
    assert measured == declared, (
        f"{language}: declared {sorted(declared)} but a build produced {sorted(measured)}"
    )


## @brief Every language row links to a page that exists.
## @return None.
## @version 1
def test_every_support_table_link_resolves() -> None:
    """THE TABLE IS THE README'S INDEX INTO THE PER-LANGUAGE DETAIL, so a dead link there is a
    reader arriving at a 404 from the first page they read.

    @brief No dead links in the generated table.
    @return None.
    @version 1
    """
    root = Path(__file__).resolve().parent.parent
    missing = {
        lang: page for lang, page in languages.DOC_PAGE.items() if not (root / page).is_file()
    }
    assert not missing, f"support-table links to pages that do not exist: {missing}"
    assert set(languages.DOC_PAGE) >= set(languages.CAPABILITIES), "a table row has no doc page"
