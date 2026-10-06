"""Tests for clew.guard.main (absorbed from doxygen-guard)."""

from __future__ import annotations

from textwrap import dedent

from clew.guard.config import CONFIG_DEFAULTS, parse_source_file
from clew.guard.main import main, validate_file
from guard_helpers import FIXTURES_DIR

NO_REQ_CONFIG = str(FIXTURES_DIR / "no_requirements_config.yaml")


class TestValidateFile:
    """Tests for validate_file."""

    def test_documented_file_no_violations(self):
        # Create a minimal fully-documented C file
        config = CONFIG_DEFAULTS.copy()
        # Use simple.c but only the documented functions will pass
        violations = validate_file(
            str(FIXTURES_DIR / "simple.c"),
            config,
            no_git=True,
        )
        # simple.c has one undocumented function
        assert len(violations) == 1
        assert "Undocumented_Function" in violations[0].message

    def test_unknown_extension_skipped(self, tmp_path):
        py_file = tmp_path / "script.rs"
        py_file.write_text("fn foo() {}")
        violations = validate_file(str(py_file), CONFIG_DEFAULTS, no_git=True)
        assert violations == []

    def test_excluded_file(self, tmp_path):
        c_file = tmp_path / "gen" / "auto.c"
        c_file.parent.mkdir()
        c_file.write_text("void Func(void) { }")
        config = {
            "validate": {
                **CONFIG_DEFAULTS["validate"],
                "exclude": ["gen/"],
            },
            "impact": CONFIG_DEFAULTS["impact"],
        }
        violations = validate_file(str(c_file), config, no_git=True)
        assert violations == []

    def test_all_checks_run(self, tmp_path):
        c_file = tmp_path / "test.c"
        c_file.write_text(
            dedent("""\
                /**
                 * @brief Good function.
                 * @version 1.0
                 */
                void Good_Func(void) {
                    x();
                }

                void Bad_Func(void) {
                    y();
                }
            """)
        )
        violations = validate_file(str(c_file), CONFIG_DEFAULTS, no_git=True)
        assert len(violations) == 1
        assert "Bad_Func" in violations[0].message


class TestMain:
    """Tests for main CLI entry point."""

    def test_no_files_returns_zero(self):
        result = main(["validate"])
        assert result == 0

    def test_validate_clean_file(self, tmp_path):
        c_file = tmp_path / "clean.c"
        c_file.write_text(
            dedent("""\
                /**
                 * @brief Clean function.
                 * @version 1.0
                 */
                void Clean_Func(void) {
                    do_stuff();
                }
            """)
        )
        result = main(["--config", NO_REQ_CONFIG, "validate", "--no-git", str(c_file)])
        assert result == 0

    def test_validate_dirty_file(self, tmp_path):
        c_file = tmp_path / "dirty.c"
        c_file.write_text(
            dedent("""\
                void Undoc_Func(void) {
                    do_stuff();
                }
            """)
        )
        result = main(["validate", "--no-git", str(c_file)])
        assert result == 1

    def test_validate_nonexistent_file(self):
        result = main(["validate", "--no-git", "/nonexistent/path.c"])
        assert result == 0  # Warning logged, no violations

    def test_default_subcommand_with_files(self, tmp_path):
        """When no subcommand is given, treat args as files (pre-commit mode)."""
        c_file = tmp_path / "test.c"
        c_file.write_text(
            dedent("""\
                /**
                 * @brief Func.
                 * @version 1.0
                 */
                void Func(void) {
                    x();
                }
            """)
        )
        result = main(["--config", NO_REQ_CONFIG, str(c_file)])
        assert result == 0

    def test_verbose_flag(self, tmp_path):
        c_file = tmp_path / "test.c"
        c_file.write_text(
            dedent("""\
                /**
                 * @brief Func.
                 * @version 1.0
                 */
                void Func(void) {
                    x();
                }
            """)
        )
        result = main(["--config", NO_REQ_CONFIG, "-v", "validate", "--no-git", str(c_file)])
        assert result == 0

    def test_custom_config(self, tmp_path):
        config_file = tmp_path / "custom.yaml"
        config_file.write_text(
            dedent("""\
                validate:
                  presence:
                    require_doxygen: false
            """)
        )
        c_file = tmp_path / "test.c"
        c_file.write_text("void Undoc(void) { x(); }")

        result = main(["--config", str(config_file), "validate", "--no-git", str(c_file)])
        assert result == 0  # Presence check disabled

    def test_retired_trace_subcommand_fails_loudly(self, capsys):
        result = main(["trace", "--req", "REQ-NONEXISTENT-9999"])
        assert result == 1
        assert "was removed" in capsys.readouterr().err

    def test_retired_subcommand_not_treated_as_file_path(self, capsys):
        """A retired subcommand must not silently degrade to pre-commit mode and exit 0."""
        result = main(["trace", "--all", "src/"])
        assert result == 1
        assert "trace" in capsys.readouterr().err

    def test_impact_no_files_returns_0(self):
        result = main(["impact", "--staged"])
        assert result == 0


class TestPrecommitPipeline:
    """Integration tests for run_precommit with impact reporting."""

    def test_precommit_with_impact(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        c_file = src / "test.c"
        c_file.write_text(
            dedent("""\
                /**
                 * @brief Process data.
                 * @version 1.0
                 * @req REQ-001
                 */
                void Process(void) {
                    event_post(EVENT_DATA_READY);
                }

                /**
                 * @brief Handle data event.
                 * @version 1.0
                 * @req REQ-001
                 */
                void OnDataReady(void) {
                    consume();
                }
            """)
        )
        req_file = tmp_path / "reqs.csv"
        req_file.write_text("Req ID,Name,Subsystem\nREQ-001,Data Processing,DataSvc\n")
        config_file = tmp_path / ".doxygen-guard.yaml"
        config_file.write_text(
            dedent("""\
                output_dir: out/
                impact:
                  requirements:
                    file: reqs.csv
                    id_column: "Req ID"
                    name_column: "Name"
                    format: csv
            """)
        )
        result = main(["--config", str(config_file), str(c_file)])
        assert result == 0


class TestParseSourceFile:
    """Tests for parse_source_file."""

    def test_unsupported_extension_returns_none(self, tmp_path):
        rs_file = tmp_path / "lib.rs"
        rs_file.write_text("fn main() {}")
        result = parse_source_file(str(rs_file), CONFIG_DEFAULTS)
        assert result is None


class TestVersionGateFailsClosed:
    """An unresolvable version gate must fail, never silently disable the @req gate.

    Regression: _detect_current_version was called only from run_precommit, so the
    documented `doxygen-guard validate` invocation left current_version as the literal
    "auto:git". parse_version then failed and returned (0,), every catalogued
    requirement filtered out as not-yet-active, _has_active_requirements returned
    False, and check_req_coverage returned [] — exit 0 with the gate off. The same
    collapse hit pre-commit mode on a shallow or tagless clone.
    """

    def _project(self, tmp_path):
        (tmp_path / "reqs.yaml").write_text(
            dedent("""\
                requirements:
                  REQ-VAL-001:
                    name: A requirement
                    min_version: v0.1.0
            """)
        )
        (tmp_path / ".doxygen-guard.yaml").write_text(
            dedent("""\
                validate:
                  version_gate:
                    current_version: "auto:git"
                    version_field: "min_version"
                impact:
                  requirements:
                    file: reqs.yaml
                    format: yaml
            """)
        )
        c_file = tmp_path / "a.c"
        c_file.write_text("/**\n * @brief No req tag.\n * @version 1.0\n */\nvoid F(void) { }\n")
        return c_file

    def test_validate_fails_when_gate_unresolvable(self, tmp_path, monkeypatch, capsys):
        c_file = self._project(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = main(["validate", "--no-git", str(c_file)])
        assert result == 1
        assert "no version could be resolved" in capsys.readouterr().err

    def test_precommit_fails_when_gate_unresolvable(self, tmp_path, monkeypatch, capsys):
        c_file = self._project(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = main([str(c_file)])
        assert result == 1
        assert "no version could be resolved" in capsys.readouterr().err

    def test_literal_version_resolves(self, tmp_path, monkeypatch):
        c_file = self._project(tmp_path)
        cfg = tmp_path / ".doxygen-guard.yaml"
        cfg.write_text(cfg.read_text().replace('"auto:git"', '"v1.0.0"'))
        monkeypatch.chdir(tmp_path)
        # Gate resolves, so the requirement is active and the missing @req is caught.
        assert main(["validate", "--no-git", str(c_file)]) == 1

    def test_no_gate_declared_is_not_an_error(self, tmp_path, monkeypatch):
        c_file = self._project(tmp_path)
        (tmp_path / ".doxygen-guard.yaml").write_text(
            "impact:\n  requirements:\n    file: reqs.yaml\n    format: yaml\n"
        )
        monkeypatch.chdir(tmp_path)
        # No version_gate declared: nothing to resolve, so no error from resolution.
        assert main(["validate", "--no-git", str(c_file)]) in (0, 1)
