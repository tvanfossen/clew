"""Rust (rustdoc) support in the absorbed gate.

Rust is opt-in: a repo declares `validate.languages.rust`, and the declared mapping is
completed from `OPT_IN_LANGUAGE_DEFAULTS`. The block is the rustdoc outer doc comment
(`///` lines or one `/** */`), reached across `#[...]` attributes; its summary paragraph
stands in for @brief; @return is not required; test code is not gated.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from clew.guard.checks import check_version_staleness
from clew.guard.config import (
    CONFIG_DEFAULTS,
    OPT_IN_LANGUAGE_DEFAULTS,
    apply_opt_in_languages,
    deep_merge,
    load_config,
    parse_content_for_file,
)
from clew.guard.main import main, validate_file
from clew.guard.parser import parse_functions
from guard_helpers import FIXTURES_DIR, guard_yaml

RUST_FIXTURE = FIXTURES_DIR / "rust_simple.rs"


def _rust_config(**validate_overrides) -> dict:
    """CONFIG_DEFAULTS with Rust declared, merged the way load_config merges it."""
    user = {"validate": {"languages": {"rust": {}}, **validate_overrides}}
    return apply_opt_in_languages(deep_merge(CONFIG_DEFAULTS, user), user)


def _parse(source: str):
    return parse_functions(dedent(source), [], None, lang_name="rust")


class TestRustDocBlocks:
    """Which comment documents which function."""

    def test_fixture_functions_and_blocks(self):
        functions = {f.name: f for f in _parse(RUST_FIXTURE.read_text())}
        # `calibrate` has no body (a trait declaration) and the test fn is skipped.
        assert set(functions) == {
            "read_temperature",
            "reset",
            "undocumented",
            "new",
            "no_summary",
            "offset",
        }
        assert functions["undocumented"].doxygen is None
        assert functions["new"].enclosing_class == "Sensor"
        assert functions["offset"].enclosing_class == "Calibrate"

    def test_doc_reaches_across_attributes(self):
        (func,) = _parse(
            """\
            /// Adds one.
            /// @version 2
            #[inline]
            #[must_use]
            pub fn add(x: i32) -> i32 { x + 1 }
            """
        )
        assert func.doxygen is not None
        assert func.doxygen.tags["version"] == ["2"]

    def test_summary_paragraph_is_the_brief(self):
        functions = {f.name: f for f in _parse(RUST_FIXTURE.read_text())}
        assert functions["read_temperature"].doxygen.tags["brief"] == ["Read the raw temperature."]
        assert functions["reset"].doxygen.tags["brief"] == ["Reset the sensor."]
        assert "brief" not in functions["no_summary"].doxygen.tags

    def test_explicit_brief_wins_over_summary(self):
        (func,) = _parse(
            """\
            /// Summary prose.
            /// @brief The stated brief.
            /// @version 1
            fn f() {}
            """
        )
        assert func.doxygen.tags["brief"] == ["The stated brief."]

    @pytest.mark.parametrize(
        "comment",
        ["//// four slashes is a plain comment", "// a plain comment", "//! an inner doc"],
    )
    def test_non_outer_doc_comments_are_not_blocks(self, comment):
        (func,) = _parse(f"{comment}\nfn f() {{}}\n")
        assert func.doxygen is None

    def test_a_blank_line_inside_the_run_ends_the_block(self):
        (func,) = _parse(
            """\
            /// Stale note about something else.

            /// Real summary.
            /// @version 1
            fn f() {}
            """
        )
        assert func.doxygen.tags["brief"] == ["Real summary."]
        assert func.doxygen.start_line == 2

    def test_block_lines_are_zero_indexed_and_inclusive(self):
        (func,) = _parse("/// Summary.\n/// @version 1\nfn f() {}\n")
        assert (func.doxygen.start_line, func.doxygen.end_line, func.def_line) == (0, 1, 2)

    @pytest.mark.parametrize("attr", ["#[test]", "#[tokio::test]", "#[rstest]", "#[bench]"])
    def test_test_functions_are_not_gated(self, attr):
        assert _parse(f"{attr}\nfn t() {{}}\n") == []

    def test_cfg_test_module_is_not_gated(self):
        assert _parse("#[cfg(test)]\nmod tests {\n    fn helper() {}\n}\n") == []

    def test_generic_impl_names_its_self_type(self):
        (func,) = _parse(
            "impl<T> Trait for Wrapper<T> {\n    /// S.\n    /// @version 1\n    fn go(&self) {}\n}\n"
        )
        assert func.enclosing_class == "Wrapper"


class TestRustValidation:
    """The gate's verdicts on Rust source."""

    def test_rust_is_opt_in(self):
        assert validate_file(str(RUST_FIXTURE), CONFIG_DEFAULTS, no_git=True) == []

    def test_fixture_violations(self):
        violations = validate_file(str(RUST_FIXTURE), _rust_config(), no_git=True)
        messages = sorted(str(v) for v in violations)
        assert len(violations) == 2, messages
        assert any("'undocumented' has no doxygen comment" in m for m in messages)
        assert any("'no_summary' doxygen missing @brief" in m for m in messages)

    def test_return_is_not_required_for_rust(self):
        functions = {f.name: f for f in _parse(RUST_FIXTURE.read_text())}
        assert "return" not in functions["read_temperature"].doxygen.tags
        violations = validate_file(str(RUST_FIXTURE), _rust_config(), no_git=True)
        assert not any("@return" in v.message for v in violations)

    def test_return_requirement_can_be_turned_back_on(self, tmp_path):
        source = tmp_path / "lib.rs"
        source.write_text(
            "/// S.\n/// @version 1\nfn value() -> u8 { 1 }\n/// S.\n/// @version 1\nfn unit() -> () {}\n"
        )
        config = _rust_config()
        config["validate"]["languages"]["rust"]["require_return"] = True
        messages = [v.message for v in validate_file(str(source), config, no_git=True)]
        assert any("'value' doxygen missing @return" in m for m in messages)
        assert not any("'unit'" in m for m in messages)

    def test_inner_doc_satisfies_the_file_block_without_at_file(self):
        config = _rust_config(presence={"require_file_doxygen": True})
        violations = validate_file(str(RUST_FIXTURE), config, no_git=True)
        assert not any("File-level" in v.message or "file-level" in v.message for v in violations)

    def test_missing_file_block_suggests_inner_doc(self, tmp_path):
        source = tmp_path / "lib.rs"
        source.write_text("/// S.\n/// @version 1\nfn f() {}\n")
        config = _rust_config(presence={"require_file_doxygen": True})
        (violation,) = validate_file(str(source), config, no_git=True)
        assert "//!" in violation.message

    def test_staleness_detects_an_unbumped_rust_body(self):
        config = _rust_config()
        head = "/// Summary.\n/// @version 1\nfn f() -> u8 {\n    1\n}\n"
        edited = head.replace("    1", "    2")
        head_funcs = parse_content_for_file("lib.rs", head, config)
        funcs = parse_content_for_file("lib.rs", edited, config)
        (violation,) = check_version_staleness(funcs, "lib.rs", config, edited, head_funcs, head)
        assert violation.check == "version"

        bumped = edited.replace("@version 1", "@version 2")
        funcs = parse_content_for_file("lib.rs", bumped, config)
        assert check_version_staleness(funcs, "lib.rs", config, bumped, head_funcs, head) == []


class TestRustConfig:
    """Declaring Rust in .clew.yaml's guard: section."""

    def test_declaring_rust_fills_its_defaults(self, tmp_path):
        path = tmp_path / ".clew.yaml"
        path.write_text(guard_yaml("validate:\n  languages:\n    rust: {}\n"))
        rust = load_config(path)["validate"]["languages"]["rust"]
        assert rust == OPT_IN_LANGUAGE_DEFAULTS["rust"]

    def test_declared_keys_win(self, tmp_path):
        path = tmp_path / ".clew.yaml"
        path.write_text(
            guard_yaml("validate:\n  languages:\n    rust:\n      require_return: true\n")
        )
        rust = load_config(path)["validate"]["languages"]["rust"]
        assert rust["require_return"] is True
        assert rust["extensions"] == [".rs"]

    def test_undeclared_rust_is_absent(self, tmp_path):
        path = tmp_path / ".clew.yaml"
        path.write_text(guard_yaml("validate: {}\n"))
        assert "rust" not in load_config(path)["validate"]["languages"]


class TestRustEndToEnd:
    """The CLI and the git-backed staleness path, on a real repository."""

    def test_precommit_mode_flags_a_stale_rust_function(self, tmp_path, monkeypatch, capsys):
        def git(*args):
            subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

        git("init", "-q")
        git("config", "user.email", "t@example.invalid")
        git("config", "user.name", "t")
        (tmp_path / ".clew.yaml").write_text(
            guard_yaml("validate:\n  languages:\n    rust: {}\n"), encoding="utf-8"
        )
        source = tmp_path / "lib.rs"
        source.write_text("/// Summary.\n/// @version 1\nfn f() -> u8 {\n    1\n}\n")
        git("add", ".")
        git("commit", "-q", "-m", "init")
        source.write_text("/// Summary.\n/// @version 1\nfn f() -> u8 {\n    2\n}\n")

        monkeypatch.chdir(tmp_path)
        assert main(["lib.rs"]) == 1
        assert "body changed but @version was not updated" in capsys.readouterr().err

        source.write_text("/// Summary.\n/// @version 2\nfn f() -> u8 {\n    2\n}\n")
        assert main(["lib.rs"]) == 0


def test_help_without_subcommand_prints_help_and_writes_nothing(tmp_path, monkeypatch, capsys):
    """`--help` with no subcommand used to fall into pre-commit mode, which ignores unknown
    flags — so asking for help ran the gate and wrote an impact report."""
    monkeypatch.chdir(tmp_path)
    assert main(["--help"]) == 0
    assert "usage: clew guard" in capsys.readouterr().out
    assert list(Path(tmp_path).iterdir()) == []
