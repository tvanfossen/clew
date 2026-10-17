# SPDX-License-Identifier: MIT
"""The shared toolchain config and file typing, on the INDEX side.

`toolchain.toml` `[ignore].paths` and `suppress.toml` entries for every tool (`tool = "*"`,
no `rule`) leave the index; statements for clew alone, for another tool, or for a rule do
not. A binary file named like source is never read. Both are recorded in `build_meta`.

@brief Tests for toolchain exclusions and binary skipping in the build.
@version 1
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from clew.cli import _build_argparser, _run_pipeline
from clew.filetypes import binary_file, binary_files
from clew.toolchain import expand_globs, load_toolchain_config

ZIP = b"PK\x03\x04" + bytes(4096)


def _write(root: Path, rel: str, text: str = "int f(void) { return 1; }\n") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ─── load_toolchain_config ───────────────────────────────────────────────────


def test_no_files_means_nothing_declared(tmp_path):
    config = load_toolchain_config(tmp_path)
    assert not config.declared() and config.sources(tmp_path) == ""


def test_index_takes_only_all_tool_statements(tmp_path):
    (tmp_path / "toolchain.toml").write_text(
        '[ignore]\npaths = ["vendor/**"]\n[clew.ignore]\npaths = ["legacy/**"]\n'
        '[knots.ignore]\npaths = ["bench/**"]\n'
    )
    (tmp_path / "suppress.toml").write_text(
        '[[suppress]]\nname = "a"\ntool = "*"\nfile_glob = "third_party/**"\n'
        '[[suppress]]\nname = "b"\ntool = "*"\nfile = "gen.c"\n'
        '[[suppress]]\nname = "c"\ntool = "clew"\nfile_glob = "doc_only/**"\n'
        '[[suppress]]\nname = "d"\ntool = "*"\nrule = "r"\nfile = "src/x.c"\n'
        '[[suppress]]\nname = "e"\ntool = "knots"\nfile_glob = "src/**"\n'
    )
    config = load_toolchain_config(tmp_path)
    assert config.index_globs == ("vendor/**", "third_party/**", "gen.c")
    assert set(config.gate_globs) == {
        "vendor/**",
        "third_party/**",
        "gen.c",
        "legacy/**",
        "doc_only/**",
    }
    assert config.sources(tmp_path) == "toolchain.toml, suppress.toml"


def test_malformed_files_are_reported_not_raised(tmp_path):
    (tmp_path / "toolchain.toml").write_text("[ignore\n")
    (tmp_path / "suppress.toml").write_text('[[suppress]]\ntool = "*"\nfile_glob = 3\n')
    config = load_toolchain_config(tmp_path)
    assert config.index_globs == ()
    assert any("could not be read" in p for p in config.problems)


def test_a_non_list_ignore_is_reported(tmp_path):
    (tmp_path / "toolchain.toml").write_text('[ignore]\npaths = "vendor/**"\n')
    config = load_toolchain_config(tmp_path)
    assert config.index_globs == () and config.problems


# ─── expand_globs ────────────────────────────────────────────────────────────


def test_matched_directories_are_returned_whole(tmp_path):
    for rel in ("vendor/a/b.c", "vendor/c.c", "src/vendor/x.c", "src/k.c", "build/o.c", "x.min.js"):
        _write(tmp_path, rel)
    found = expand_globs(tmp_path, ("vendor/**", "build", "*.min.js"))
    assert found == sorted([tmp_path / "vendor", tmp_path / "build", tmp_path / "x.min.js"])


def test_pruned_directories_are_not_walked(tmp_path):
    _write(tmp_path, "already/vendor/x.c")
    assert expand_globs(tmp_path, ("**/x.c",), [str(tmp_path / "already")]) == []


def test_an_invalid_glob_does_not_disable_the_rest(tmp_path):
    _write(tmp_path, "vendor/x.c")
    assert expand_globs(tmp_path, ("src/[unclosed", "vendor/**")) == [tmp_path / "vendor"]


# ─── file typing ─────────────────────────────────────────────────────────────


def test_binary_named_as_source_is_detected(tmp_path):
    blob = tmp_path / "blob.c"
    blob.write_bytes(ZIP)
    skipped = binary_file(blob)
    assert skipped is not None and skipped.binary_kind == "archive"
    assert binary_file(_write(tmp_path, "ok.c")) is None


def test_empty_and_unreadable_files_are_not_skipped(tmp_path):
    empty = tmp_path / "__init__.py"
    empty.write_text("")
    assert binary_file(empty) is None, "an empty file is legitimate source"
    assert binary_file(tmp_path / "missing.c") is None, "left to the reader that opens it"


def test_binary_files_logs_each_skip(tmp_path, caplog):
    (tmp_path / "a.c").write_bytes(b"\x7fELF" + bytes(4096))
    import logging

    with caplog.at_level(logging.INFO):
        assert len(binary_files([tmp_path / "a.c", _write(tmp_path, "b.c")])) == 1
    assert "a.c" in caplog.text and "binary" in caplog.text


# ─── the build ───────────────────────────────────────────────────────────────


@pytest.mark.skipif(shutil.which("doxygen") is None, reason="builds with the real doxygen")
def test_build_honours_toolchain_config_and_skips_binaries(tmp_path):
    repo = tmp_path / "repo"
    _write(repo, "src/main.c", "int helper(int x) { return x; }\nint main(void) { return 0; }\n")
    _write(repo, "vendor/lib/v.c", "int vendored(void) { return 2; }\n")
    _write(repo, "gen/g.c", "int generated(void) { return 3; }\n")
    _write(repo, "doc_only/d.c", "int gate_only(void) { return 4; }\n")
    (repo / "src" / "blob.c").write_bytes(ZIP)
    (repo / "toolchain.toml").write_text('[ignore]\npaths = ["vendor/**"]\n')
    (repo / "suppress.toml").write_text(
        '[[suppress]]\nname = "g"\ntool = "*"\nfile_glob = "gen/**"\n'
        '[[suppress]]\nname = "d"\ntool = "clew"\nfile_glob = "doc_only/**"\n'
    )
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))

    conn = sqlite3.connect(out)
    functions = {r[0] for r in conn.execute("SELECT name FROM memberdef WHERE kind='function'")}
    assert functions == {"helper", "main", "gate_only"}, (
        "vendor/ and gen/ are excluded for every tool; doc_only/ only for clew's gate"
    )
    files = {r[0] for r in conn.execute("SELECT name FROM path WHERE type=1")}
    assert not any(name.endswith("blob.c") for name in files)
    meta = dict(conn.execute("SELECT key, value FROM build_meta WHERE key LIKE 'scope.%'"))
    assert json.loads(meta["scope.toolchain_ignores"]) == ["vendor/**", "gen/**"]
    assert meta["scope.toolchain_config"] == "toolchain.toml, suppress.toml"
    assert meta["scope.toolchain_excluded"] == "2"
    assert meta["scope.skipped_binary"] == "1"
    assert "blob.c (archive)" in meta["scope.skipped_binary_sample"]
    assert "vendor" not in meta.get("scope.operator_excludes", ""), "never replayed as operator"


# ─── B3: a declared never-walk directory is an exclusion, not a silent prune ──


def test_a_declared_never_walk_directory_is_reported_as_an_exclusion(tmp_path):
    """B3, 1.1.0 MERGE REVIEW. `node_modules`, `.git`, `.venv` and friends are in
    `_NEVER_WALK`, and the walk `continue`d on them BEFORE testing the declared globs — so a
    repository stating `node_modules/**` got back `[]`, and the index's EXCLUDE list never
    named the tree the owner had just excluded, while the gate (which matches globs directly,
    never walking) honoured it. Same declaration, two answers.

    @brief A declared `_NEVER_WALK` name is returned as an excluded path. @version 1
    """
    _write(tmp_path, "node_modules/dep/index.js", "module.exports = 1;\n")
    _write(tmp_path, "src/k.c")

    assert expand_globs(tmp_path, ("node_modules/**",)) == [tmp_path / "node_modules"]


def test_an_undeclared_never_walk_directory_is_still_pruned_silently(tmp_path):
    """THE CONTROL, and the reason the fix is "match first" rather than "stop pruning": an
    undeclared `node_modules` must not become an exclusion the owner never asked for, which
    would put every such tree into the Doxyfile's EXCLUDE and the cache key.

    @brief An undeclared never-walk name yields no exclusion. @version 1
    """
    _write(tmp_path, "node_modules/dep/index.js", "module.exports = 1;\n")
    _write(tmp_path, "vendor/x.c")

    assert expand_globs(tmp_path, ("vendor/**",)) == [tmp_path / "vendor"]


def test_the_gate_and_the_index_agree_on_one_declaration(tmp_path):
    """THE INVARIANT THAT ACTUALLY MATTERS. One `toolchain.toml` statement, two consumers:
    the gate asks `gate_exclusion` per file, the index asks `expand_globs` once per build.
    A file the gate refuses to check must be a file the index was told to exclude, or the
    repository's single statement means two different things depending on which half of clew
    read it.

    @brief Gate and index honour the same declared glob. @version 1
    """
    import os

    from clew.guard.filters import _gate_matcher, gate_exclusion

    target = _write(tmp_path, "node_modules/dep/index.js", "module.exports = 1;\n")
    _write(tmp_path, "src/k.c")
    (tmp_path / "toolchain.toml").write_text('[ignore]\npaths = ["node_modules/**"]\n')
    config = load_toolchain_config(tmp_path)

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        _gate_matcher.cache_clear()
        gate_reason = gate_exclusion("node_modules/dep/index.js")
    finally:
        os.chdir(cwd)
        _gate_matcher.cache_clear()

    excluded = expand_globs(tmp_path, config.index_globs)

    assert gate_reason is not None, "the gate must skip it; this test is about the other half"
    assert any(target == path or path in target.parents for path in excluded), (
        f"the gate skips {target} but the index was handed no exclusion covering it: {excluded}"
    )
