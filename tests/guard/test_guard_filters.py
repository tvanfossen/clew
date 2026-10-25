"""The gate honours the shared toolchain config and skips binary files.

toolchain.toml `[ignore].paths` and `[clew.ignore].paths`, and suppress.toml entries for
`tool = "*"` or `"clew"` with no `rule`, exclude files from validation and from the
`files` / `coverage` walks; a binary file named like source is never parsed.
"""

from __future__ import annotations

import pytest

from clew.guard import filters
from clew.guard.config import CONFIG_DEFAULTS
from clew.guard.contract import build_files_contract
from clew.guard.main import validate_file

UNDOCUMENTED = "int f(void) { return 1; }\n"


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    filters._gate_matcher.cache_clear()
    yield tmp_path
    filters._gate_matcher.cache_clear()


def _write(root, rel, text=UNDOCUMENTED):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return rel


def test_without_toolchain_files_everything_is_checked(repo):
    rel = _write(repo, "vendor/v.c")
    assert validate_file(rel, CONFIG_DEFAULTS, no_git=True)


def test_toolchain_ignore_paths_skip_validation(repo):
    (repo / "toolchain.toml").write_text('[ignore]\npaths = ["vendor/**"]\n')
    assert validate_file(_write(repo, "vendor/lib/v.c"), CONFIG_DEFAULTS, no_git=True) == []
    assert validate_file(_write(repo, "src/s.c"), CONFIG_DEFAULTS, no_git=True)


def test_clew_specific_ignores_apply_to_the_gate(repo):
    (repo / "toolchain.toml").write_text('[clew.ignore]\npaths = ["legacy/**"]\n')
    (repo / "suppress.toml").write_text(
        '[[suppress]]\nname = "gen"\ntool = "clew"\nfile_glob = "gen/*.c"\n'
        '[[suppress]]\nname = "knots only"\ntool = "knots"\nfile_glob = "src/**"\n'
        '[[suppress]]\nname = "a rule"\ntool = "clew"\nrule = "presence"\nfile = "src/s.c"\n'
    )
    assert validate_file(_write(repo, "legacy/l.c"), CONFIG_DEFAULTS, no_git=True) == []
    assert validate_file(_write(repo, "gen/g.c"), CONFIG_DEFAULTS, no_git=True) == []
    # Another tool's entry, and an entry scoped to a rule, exclude nothing.
    assert validate_file(_write(repo, "src/s.c"), CONFIG_DEFAULTS, no_git=True)


def test_binary_named_as_source_is_skipped(repo):
    (repo / "blob.c").write_bytes(b"PK\x03\x04" + bytes(4096))
    assert validate_file("blob.c", CONFIG_DEFAULTS, no_git=True) == []


def test_files_contract_reports_and_applies_toolchain_ignores(repo):
    (repo / "toolchain.toml").write_text('[ignore]\npaths = ["vendor/**"]\n')
    _write(repo, "vendor/v.c")
    _write(repo, "src/s.c")
    (repo / "src" / "blob.c").write_bytes(b"\x7fELF" + bytes(4096))
    contract = build_files_contract(["."], CONFIG_DEFAULTS)
    assert contract["toolchain_config"] == "toolchain.toml"
    assert contract["toolchain_ignores"] == ["vendor/**"]
    assert [f.replace("\\", "/") for f in contract["files"]] == ["src/s.c"]


def test_a_broken_toolchain_file_is_reported_not_fatal(repo, caplog):
    (repo / "toolchain.toml").write_text("[ignore\npaths = \n")
    assert validate_file(_write(repo, "src/s.c"), CONFIG_DEFAULTS, no_git=True)
    assert "could not be read" in caplog.text
